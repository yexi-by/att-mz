"""插件源码文本风险扫描、规则提取和写回测试。"""
# pyright: reportPrivateUsage=false

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn, cast

import pytest

import app.plugin_source_text as plugin_source_text_package
import app.plugin_source_text.runtime_audit as plugin_source_runtime_audit
import app.plugin_source_text.scanner as plugin_source_text_scanner
from app.application.flow_gate import (
    collect_workflow_gate_errors,
    event_command_rule_scope_hash_for_setting,
    normal_placeholder_scope_hash,
    note_tag_rule_scope_hash_for_text_rules,
    structured_placeholder_scope_hash,
)
from app.agent_toolkit import AgentToolkitService
from app.config.schemas import Setting, TextRulesSetting
from app.native_javascript_ast import NativeRuntimeLiteralIssueFact, NativeRuntimeLiteralIssueInput
from app.native_scope_index import (
    NativeRuleCandidatesResult,
    scan_native_rule_candidates as real_scan_native_rule_candidates,
)
from app.persistence import GameRegistry, TargetGameSession
from app.plugin_source_text import (
    PluginSourceScan,
    PluginSourceTextExtraction,
    audit_active_runtime_plugin_source,
    build_native_plugin_source_scan,
    build_plugin_source_rule_records_from_import,
    plugin_source_location_path,
    parse_plugin_source_rule_import_text,
    plugin_source_rule_records_to_import_json,
)
from app.plugin_source_text.scanner import (
    PluginSourceBatchTextScan,
    build_plugin_source_file_hash,
    iter_plugin_source_string_literals,
    clear_plugin_source_native_scan_cache,
    scan_plugin_source_runtime_files_text_strict,
)
from app.plugin_source_text.runtime_mapping import plugin_source_runtime_hash_lines, plugin_source_runtime_hash_text
from app.rmmz import load_active_game_data, load_game_data
from app.rmmz.schema import GameData, PluginSourceRuntimeWriteMapRecord, PluginSourceTextRuleRecord, TranslationItem
from app.rmmz.source_snapshot import create_source_snapshot_for_clean_game
from app.rmmz.text_rules import JsonObject, JsonValue, TextRules, coerce_json_value, ensure_json_array, ensure_json_object
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    plugin_rule_scope_hash,
)
from app.terminology import TerminologyGlossary, TerminologyRegistry
from app.text_scope import TextScopeService
from app.text_scope.write_probe import collect_write_back_probe_reasons
from app.utils.config_loader_utils import load_setting
from tests._native_write_plan_helper import (
    _write_temp_db,
    reset_writable_copies,
    write_data_text,
    write_game_files,
    write_plugin_source_text,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


def test_plugin_source_scanner_public_surface_is_current() -> None:
    """包根只暴露业务级插件源码能力，低层 scanner API 留在 scanner 模块内。"""
    removed_names = {
        "build_plugin_source_scan",
        "scan_plugin_source_files_text_strict",
        "_build_legacy_plugin_source_scan",
        "_scan_legacy_plugin_source_files_text_strict",
        "find_candidate_by_selector",
        "scan_plugin_source_file_text",
        "scan_plugin_source_file_text_strict",
    }
    scanner_internal_names = {
        "PluginSourceBatchTextScan",
        "build_plugin_source_file_hash",
        "clear_plugin_source_native_scan_cache",
        "iter_plugin_source_string_literals",
        "scan_plugin_source_runtime_files_text_strict",
    }

    for name in removed_names:
        assert name not in plugin_source_text_package.__all__
        assert name not in plugin_source_text_scanner.__all__
        assert not hasattr(plugin_source_text_package, name)
        assert not hasattr(plugin_source_text_scanner, name)
    assert scanner_internal_names.isdisjoint(plugin_source_text_package.__all__)
    assert scanner_internal_names <= set(plugin_source_text_scanner.__all__)


@pytest.mark.asyncio
async def test_native_write_plan_helper_writes_migrated_event_command_fact_with_render_parts(
    minimal_game_dir: Path,
) -> None:
    """native 写回测试 helper 不能用 test_helper domain 绕过迁移域 render parts 校验。"""
    game_data = await load_game_data(minimal_game_dir)
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="long_text",
        role="アリス",
        original_lines=["こんにちは"],
        source_line_paths=["CommonEvents.json/1/1"],
        translation_lines=["你好"],
    )

    db_path = _write_temp_db(
        game_data=game_data,
        content_root=game_data.layout.content_root,
        items=[item],
        speaker_name_translations=None,
        terminology_registry=None,
        mv_virtual_namebox_rule_records=None,
        plugin_source_rule_records=None,
    )
    try:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        try:
            fact_row = cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT fact_id, domain, raw_text FROM text_facts_v2 WHERE location_path = ?",
                    (item.location_path,),
                ).fetchone(),
            )
            assert fact_row is not None
            assert fact_row["domain"] == "event_command"
            part_rows = cast(
                list[sqlite3.Row],
                connection.execute(
                    """
--sql
                SELECT part_kind, raw_text, semantic_text, template_key
                FROM text_fact_render_parts_v2
                WHERE fact_id = ?
                ORDER BY part_order
                ;
                """,
                    (fact_row["fact_id"],),
                ).fetchall(),
            )
            assert [
                (row["part_kind"], row["raw_text"], row["semantic_text"], row["template_key"])
                for row in part_rows
            ] == [("translated_body", "こんにちは", "こんにちは", "body")]
            rendered_raw = "".join(cast(str, row["raw_text"]) for row in part_rows)
            assert rendered_raw == cast(str, fact_row["raw_text"])
        finally:
            connection.close()
    finally:
        db_path.unlink(missing_ok=True)


def _rewrite_plugins_js(path: Path, plugins: list[JsonValue]) -> None:
    """把插件数组写回测试用 plugins.js。"""
    _ = path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )


def _forbid_legacy_plugin_source_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """禁止本轮默认路径回到旧 Python 插件源码主扫描。"""

    def forbidden_scan(*args: object, **kwargs: object) -> PluginSourceScan:
        _ = (args, kwargs)
        raise AssertionError("默认路径不应调用旧 Python 插件源码主扫描")

    for target in (
        "app.agent_toolkit.services.quality.build_plugin_source_scan",
        "app.application.flow_gate.build_plugin_source_scan",
        "app.text_scope.builder.build_plugin_source_scan",
        "app.plugin_source_text.extraction.build_plugin_source_scan",
        "app.plugin_source_text.rules.build_plugin_source_scan",
        "app.plugin_source_text.importer.build_plugin_source_scan",
    ):
        monkeypatch.setattr(target, forbidden_scan, raising=False)


async def _install_minimal_external_workflow_reviews(
    *,
    registry: GameRegistry,
    game_title: str,
    game_dir: Path,
) -> None:
    """为插件源码测试补齐无关外部规则 gate，隔离源码分支断言。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    game_data = await load_game_data(game_dir)
    text_rules = TextRules.from_setting(setting.text_rules)
    async with await registry.open_game(game_title) as session:
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )
        await session.replace_rule_review_state(
            rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
            scope_hash=plugin_rule_scope_hash(game_data),
            reviewed_empty=True,
        )
        await session.replace_rule_review_state(
            rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
            scope_hash=event_command_rule_scope_hash_for_setting(
                game_data=game_data,
                setting=setting,
            ),
            reviewed_empty=True,
        )
        await session.replace_rule_review_state(
            rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
            scope_hash=note_tag_rule_scope_hash_for_text_rules(
                game_data=game_data,
                text_rules=text_rules,
            ),
            reviewed_empty=True,
        )
        await session.replace_rule_review_state(
            rule_domain=PLACEHOLDER_RULE_DOMAIN,
            scope_hash=normal_placeholder_scope_hash(
                translation_data_map=scope.translation_data_map,
                text_rules=text_rules,
            ),
            reviewed_empty=True,
        )
        await session.replace_rule_review_state(
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            scope_hash=structured_placeholder_scope_hash(
                translation_data_map=scope.translation_data_map,
                structured_rules=text_rules.structured_placeholder_rules,
            ),
            reviewed_empty=True,
        )


def _create_test_source_snapshot(game_data: GameData) -> None:
    """为写回测试显式模拟注册流程已经创建的可信源快照。"""
    layout = game_data.layout
    if (
        layout.data_origin_dir.is_dir()
        and layout.plugins_origin_path.is_file()
        and layout.plugin_source_origin_dir.is_dir()
    ):
        return
    create_source_snapshot_for_clean_game(layout)


@pytest.mark.asyncio
async def test_plugin_source_scan_only_counts_enabled_direct_plugin_files(minimal_game_dir: Path) -> None:
    """插件源码风险只用启用插件的直接源码文件触发高风险。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.extend(
        [
            {
                "name": "EnabledSource",
                "status": True,
                "description": "",
                "parameters": {},
            },
            {
                "name": "DisabledSource",
                "status": False,
                "description": "",
                "parameters": {},
            },
        ]
    )
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    enabled_lines = [
        f"Window_Base.prototype.drawText('有効テキスト{i}', 0, 0, 320);"
        for i in range(301)
    ]
    disabled_lines = [
        f"Window_Base.prototype.drawText('無効テキスト{i}', 0, 0, 320);"
        for i in range(301)
    ]
    _ = (plugin_source_dir / "EnabledSource.js").write_text("\n".join(enabled_lines), encoding="utf-8")
    _ = (plugin_source_dir / "DisabledSource.js").write_text("\n".join(disabled_lines), encoding="utf-8")
    nested_dir = plugin_source_dir / "nested"
    nested_dir.mkdir()
    _ = (nested_dir / "EnabledSource.js").write_text(
        "Window_Base.prototype.drawText('入れ子は対象外', 0, 0, 320);",
        encoding="utf-8",
    )

    game_data = await load_game_data(minimal_game_dir)
    text_rules = TextRules.from_setting(TextRulesSetting())
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)

    assert scan.risk.high_risk
    assert scan.risk.strong_context_text_count == 301
    assert scan.risk.ignored_file_count == 1
    assert scan.risk.scanned_file_count == 4
    assert all(candidate.file_name != "nested/EnabledSource.js" for candidate in scan.candidates)


@pytest.mark.asyncio
async def test_plugin_source_scan_batches_native_ast_parse_for_source_files(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码总扫描必须批量调用 Rust AST，而不是按文件逐个进入 Python/Rust 边界。"""
    clear_plugin_source_native_scan_cache()
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.extend(
        [
            {"name": "BatchA", "status": True, "description": "", "parameters": {}},
            {"name": "BatchB", "status": True, "description": "", "parameters": {}},
        ]
    )
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "BatchA.js").write_text(
        "Window_Base.prototype.drawText('一括テキストA', 0, 0, 320);",
        encoding="utf-8",
    )
    _ = (plugin_source_dir / "BatchB.js").write_text(
        "Window_Base.prototype.drawText('一括テキストB', 0, 0, 320);",
        encoding="utf-8",
    )
    batch_calls: list[tuple[str, ...]] = []

    def counting_batch_scan(files: dict[str, str]) -> object:
        """记录批量入口，并用真实单文件解析器构造等价返回值。"""
        batch_calls.append(tuple(sorted(files)))
        from app.native_javascript_ast import parse_native_javascript_string_spans

        return {
            file_name: parse_native_javascript_string_spans(source)
            for file_name, source in files.items()
        }

    def forbidden_single_scan(source: str) -> object:
        """总扫描不应按文件反复调用单文件适配入口。"""
        _ = source
        raise AssertionError("插件源码总扫描不应调用单文件 AST 入口")

    monkeypatch.setattr(
        "app.plugin_source_text.scanner.parse_native_javascript_string_spans_batch",
        counting_batch_scan,
    )
    monkeypatch.setattr(
        "app.plugin_source_text.scanner.parse_native_javascript_string_spans",
        forbidden_single_scan,
    )
    game_data = await load_game_data(minimal_game_dir)
    scan = scan_plugin_source_runtime_files_text_strict(
        files=game_data.plugin_source_files,
        active_file_names=frozenset({"BatchA.js", "BatchB.js"}),
    )

    assert len(batch_calls) == 1
    assert {"BatchA.js", "BatchB.js"} <= set(batch_calls[0])
    assert {"BatchA.js", "BatchB.js"} <= set(scan.file_scans)


@pytest.mark.asyncio
async def test_plugin_source_scan_reuses_native_ast_by_file_hash(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """相同源码 hash 的插件源码扫描复用 Rust AST 结果。"""
    clear_plugin_source_native_scan_cache()
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.extend(
        [
            {"name": "HashCacheA", "status": True, "description": "", "parameters": {}},
            {"name": "HashCacheB", "status": True, "description": "", "parameters": {}},
        ]
    )
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source = "const Messages = { title: 'ハッシュキャッシュ本文' };\n"
    _ = (plugin_source_dir / "HashCacheA.js").write_text(source, encoding="utf-8")
    _ = (plugin_source_dir / "HashCacheB.js").write_text(source, encoding="utf-8")
    batch_calls: list[tuple[str, ...]] = []

    def counting_batch_scan(files: Mapping[str, str]) -> object:
        batch_calls.append(tuple(sorted(files)))
        from app.native_javascript_ast import parse_native_javascript_string_spans

        return {
            file_name: parse_native_javascript_string_spans(file_source)
            for file_name, file_source in files.items()
        }

    monkeypatch.setattr(
        "app.plugin_source_text.scanner.parse_native_javascript_string_spans_batch",
        counting_batch_scan,
    )
    game_data = await load_game_data(minimal_game_dir)
    active_file_names = frozenset({"HashCacheA.js", "HashCacheB.js"})
    first_scan = scan_plugin_source_runtime_files_text_strict(
        files=game_data.plugin_source_files,
        active_file_names=active_file_names,
    )
    second_scan = scan_plugin_source_runtime_files_text_strict(
        files=game_data.plugin_source_files,
        active_file_names=active_file_names,
    )

    assert len(batch_calls) == 1
    assert "HashCacheA.js" in batch_calls[0]
    assert "HashCacheB.js" not in batch_calls[0]
    assert {"HashCacheA.js", "HashCacheB.js"} <= set(first_scan.file_scans)
    assert {"HashCacheA.js", "HashCacheB.js"} <= set(second_scan.file_scans)


@pytest.mark.asyncio
async def test_plugin_source_rules_extract_and_write_back_ast_string(minimal_game_dir: Path) -> None:
    """插件源码规则按 AST selector 提取文本，并按同一 selector 写回源码。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append(
        {
            "name": "HardcodedText",
            "status": True,
            "description": "",
            "parameters": {},
        }
    )
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source_path = plugin_source_dir / "HardcodedText.js"
    _ = source_path.write_text(
        "\n".join(
            [
                "const Messages = {",
                "  title: 'プラグイン直書き',",
                "  helpLines: ['一行目', '二行目'],",
                "};",
                "Window_Base.prototype.drawText(Messages.title, 0, 0, 320);",
            ]
        ),
        encoding="utf-8",
    )
    game_data = await load_game_data(minimal_game_dir)
    text_rules = TextRules.from_setting(TextRulesSetting())
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    title_candidate = next(candidate for candidate in scan.candidates if candidate.text == "プラグイン直書き")
    rule_text = json.dumps(
        [
            {
                "file": "HardcodedText.js",
                "selectors": [title_candidate.selector],
            }
        ],
        ensure_ascii=False,
    )
    records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(rule_text),
        text_rules=text_rules,
    )

    extracted = PluginSourceTextExtraction(game_data, records, text_rules).extract_all_text()
    items = extracted["js/plugins/HardcodedText.js"].translation_items
    assert [item.original_lines for item in items] == [["プラグイン直書き"]]

    items[0].translation_lines = ["插件直写"]
    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    _ = write_plugin_source_text(
        game_data,
        items,
        text_rules=text_rules,
    )
    write_game_files(game_data)

    assert "title: '插件直写'" in source_path.read_text(encoding="utf-8")
    backup_path = minimal_game_dir / "js" / "plugins_source_origin" / "HardcodedText.js"
    assert backup_path.exists()
    assert "title: 'プラグイン直書き'" in backup_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_plugin_source_extraction_allows_stale_rule_hash_when_selector_matches(
    minimal_game_dir: Path,
) -> None:
    """插件源码规则文件 hash 只做诊断；selector 和原文仍命中时可以继续提取。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { title: 'プラグイン直書き' };\n",
        encoding="utf-8",
    )
    game_data = await load_game_data(minimal_game_dir)
    text_rules = TextRules.from_setting(TextRulesSetting())
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    candidate = next(candidate for candidate in scan.candidates if candidate.file_name == "HardcodedText.js")
    record = PluginSourceTextRuleRecord(
        file_name="HardcodedText.js",
        file_hash="stale-hash",
        selectors=[candidate.selector],
    )

    extracted = PluginSourceTextExtraction(game_data, [record], text_rules).extract_all_text()

    item = extracted["js/plugins/HardcodedText.js"].translation_items[0]
    assert item.location_path == plugin_source_location_path(
        file_name="HardcodedText.js",
        selector=candidate.selector,
    )
    assert item.original_lines == ["プラグイン直書き"]


@pytest.mark.asyncio
async def test_plugin_source_extraction_rejects_missing_selector_after_source_change(
    minimal_game_dir: Path,
) -> None:
    """插件源码规则 selector 失效时仍必须显式报过期。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source_path = plugin_source_dir / "HardcodedText.js"
    _ = source_path.write_text(
        "const Messages = { title: 'プラグイン直書き' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    initial_game_data = await load_game_data(minimal_game_dir)
    initial_scan = build_native_plugin_source_scan(game_data=initial_game_data, text_rules=text_rules)
    initial_candidate = next(candidate for candidate in initial_scan.candidates if candidate.file_name == "HardcodedText.js")
    _ = source_path.write_text(
        "const Messages = { title: '変更後プラグイン直書き' };\n",
        encoding="utf-8",
    )
    changed_game_data = await load_game_data(minimal_game_dir)
    record = PluginSourceTextRuleRecord(
        file_name="HardcodedText.js",
        file_hash="stale-hash",
        selectors=[initial_candidate.selector],
    )

    with pytest.raises(RuntimeError, match="插件源码规则已过期"):
        _ = PluginSourceTextExtraction(changed_game_data, [record], text_rules).extract_all_text()


@pytest.mark.asyncio
async def test_plugin_source_ast_map_exports_short_source_text_with_ast_context(
    minimal_game_dir: Path,
) -> None:
    """插件源码 AST 地图必须导出所有源语言短文本，并附加事实 AST 上下文。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "\n".join(
            [
                "const Commands = {",
                "  param2: ['プフクスッ', '終わりね。', '早いですねー。'],",
                "  icon: 'img/日本語.png',",
                "};",
                "function termSecondPerson(targetId) {",
                "  return 'キミ';",
                "}",
                "Window_Base.prototype.drawText('短い', 0, 0, 320);",
            ]
        ),
        encoding="utf-8",
    )
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(
        game_data=game_data,
        text_rules=TextRules.from_setting(TextRulesSetting()),
    )
    candidates_by_text = {candidate.text: candidate for candidate in scan.candidates}

    for text in ["プフクスッ", "終わりね。", "早いですねー。", "img/日本語.png", "キミ", "短い"]:
        assert text in candidates_by_text

    param_candidate = candidates_by_text["プフクスッ"]
    assert param_candidate.ast_context["property_key"] == "param2"
    assert param_candidate.ast_context["property_path"] == ["param2"]
    return_candidate = candidates_by_text["キミ"]
    assert return_candidate.ast_context["return_function_name"] == "termSecondPerson"
    call_candidate = candidates_by_text["短い"]
    call_name = call_candidate.ast_context["call_name"]
    assert isinstance(call_name, str)
    assert call_name.endswith("drawText")
    assert call_candidate.ast_context["call_argument_index"] == 0
    resource_candidate = candidates_by_text["img/日本語.png"]
    assert "resource_path_like" in resource_candidate.structural_flags


@pytest.mark.asyncio
async def test_plugin_source_extraction_scans_each_file_once(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一插件源码文件的多条 selector 提取时只能解析一次源码。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('抽出テキスト{i}', 0, 0, 320);"
            for i in range(5)
        ),
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    file_scan = next(file_scan for file_scan in scan.files if file_scan.file_name == "HardcodedText.js")
    selectors = [candidate.selector for candidate in scan.candidates if candidate.file_name == "HardcodedText.js"]
    record = PluginSourceTextRuleRecord(
        file_name="HardcodedText.js",
        file_hash=file_scan.file_hash,
        selectors=selectors,
    )
    clear_plugin_source_native_scan_cache()
    legacy_ast_count = 0
    native_scan_count = 0

    from app.native_javascript_ast import NativeJavaScriptStringScan, parse_native_javascript_string_spans_batch

    def counting_native_batch(files: Mapping[str, str]) -> dict[str, NativeJavaScriptStringScan]:
        """统计源码提取阶段调用批量原生 AST 的次数。"""
        nonlocal legacy_ast_count
        legacy_ast_count += 1
        return parse_native_javascript_string_spans_batch(files)

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    monkeypatch.setattr(
        "app.plugin_source_text.scanner.parse_native_javascript_string_spans_batch",
        counting_native_batch,
    )
    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )

    extracted = PluginSourceTextExtraction(game_data, [record], text_rules).extract_all_text()

    assert len(extracted["js/plugins/HardcodedText.js"].translation_items) == len(selectors)
    assert native_scan_count == 1
    assert legacy_ast_count == 0


@pytest.mark.asyncio
async def test_plugin_source_write_back_scans_changed_file_for_runtime_write_maps(
    minimal_game_dir: Path,
) -> None:
    """插件源码写回只为实际写入的文件生成当前运行映射。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('回写テキスト{i}', 0, 0, 320);"
            for i in range(3)
        ),
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    file_scan = next(file_scan for file_scan in scan.files if file_scan.file_name == "HardcodedText.js")
    selectors = [candidate.selector for candidate in scan.candidates if candidate.file_name == "HardcodedText.js"]
    record = PluginSourceTextRuleRecord(
        file_name="HardcodedText.js",
        file_hash=file_scan.file_hash,
        selectors=selectors,
    )
    items = PluginSourceTextExtraction(game_data, [record], text_rules).extract_all_text()[
        "js/plugins/HardcodedText.js"
    ].translation_items
    for index, item in enumerate(items):
        item.translation_lines = [f"写回文本{index}"]
    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    runtime_write_maps = write_plugin_source_text(
        game_data,
        items,
        text_rules=text_rules,
    )

    assert len(runtime_write_maps) == len(items)
    assert {record.source_file_name for record in runtime_write_maps} == {"HardcodedText.js"}


@pytest.mark.asyncio
async def test_data_write_back_ignores_plugin_source_location_paths(minimal_game_dir: Path) -> None:
    """Rust 写回计划遇到失效插件源码路径必须直接报错。"""
    game_data = await load_game_data(minimal_game_dir)
    item = TranslationItem(
        location_path="js/plugins/HardcodedText.js/ast:string:1:2:abcdef",
        item_type="short_text",
        original_lines=["プラグイン直書き"],
        source_line_paths=["js/plugins/HardcodedText.js/ast:string:1:2:abcdef"],
        translation_lines=["插件直写"],
    )

    _create_test_source_snapshot(game_data)
    with pytest.raises(ValueError, match="插件源码读取失败"):
        write_data_text(game_data, [item], text_rules=TextRules.from_setting(TextRulesSetting()))


@pytest.mark.asyncio
async def test_non_utf8_plugin_source_does_not_break_default_game_loading(minimal_game_dir: Path) -> None:
    """非 UTF-8 插件源码不能让普通游戏加载和低成本扫描直接失败。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "ShiftJisSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "ShiftJisSource.js").write_bytes(
        "Window_Base.prototype.drawText('シフトJIS本文', 0, 0, 320);".encode("cp932")
    )

    game_data = await load_game_data(minimal_game_dir)
    light_game_data = await load_game_data(minimal_game_dir, include_plugin_source_files=False)
    scan = build_native_plugin_source_scan(
        game_data=game_data,
        text_rules=TextRules.from_setting(TextRulesSetting()),
    )

    assert light_game_data.plugin_source_files == {}
    assert light_game_data.plugin_source_read_errors == {}
    assert "ShiftJisSource.js" not in game_data.plugin_source_files
    assert game_data.plugin_source_read_errors["ShiftJisSource.js"]
    assert scan.risk.read_error_file_count == 1


def test_plugin_source_rule_import_rejects_extra_fields() -> None:
    """插件源码规则 JSON 只能包含最小 schema 字段。"""
    rule_text = json.dumps(
        [
            {
                "file": "HardcodedText.js",
                "selectors": ["ast:string:1:2:abcdef"],
                "source": "不允许把源码内容写进规则",
            }
        ],
        ensure_ascii=False,
    )

    with pytest.raises(Exception, match="source"):
        _ = parse_plugin_source_rule_import_text(rule_text)


@pytest.mark.asyncio
async def test_plugin_source_rules_support_excluded_selectors(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码规则可保存已审查但不翻译的 selector，且不进入正文提取。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "\n".join(
            [
                "const Messages = { title: '翻訳する本文', icon: 'img/日本語.png' };",
            ]
        ),
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    title_candidate = next(candidate for candidate in scan.candidates if candidate.text == "翻訳する本文")
    icon_candidate = next(candidate for candidate in scan.candidates if candidate.text == "img/日本語.png")
    rule_text = json.dumps(
        [
            {
                "file": "HardcodedText.js",
                "selectors": [title_candidate.selector],
                "excluded_selectors": [icon_candidate.selector],
            }
        ],
        ensure_ascii=False,
    )

    records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(rule_text),
        text_rules=text_rules,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_source_text_rules(records)
        persisted_records = await session.read_plugin_source_text_rules()
    extracted = PluginSourceTextExtraction(game_data, persisted_records, text_rules).extract_all_text()
    exported_rules = plugin_source_rule_records_to_import_json(persisted_records)
    exported_rule = ensure_json_object(ensure_json_array(exported_rules, "rules")[0], "rules[0]")

    assert persisted_records[0].selectors == [title_candidate.selector]
    assert persisted_records[0].excluded_selectors == [icon_candidate.selector]
    assert extracted["js/plugins/HardcodedText.js"].translation_items[0].original_lines == ["翻訳する本文"]
    assert exported_rule["excluded_selectors"] == [icon_candidate.selector]


@pytest.mark.asyncio
async def test_plugin_source_rules_allow_file_with_only_excluded_selectors(
    minimal_game_dir: Path,
) -> None:
    """插件源码文件可以只保存排除 selector，用来表示已审查但不翻译。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { icon: 'img/日本語.png' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    candidate = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates[0]
    rule_text = json.dumps(
        [
            {
                "file": "HardcodedText.js",
                "selectors": [],
                "excluded_selectors": [candidate.selector],
            }
        ],
        ensure_ascii=False,
    )

    records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(rule_text),
        text_rules=text_rules,
    )

    assert records[0].selectors == []
    assert records[0].excluded_selectors == [candidate.selector]


@pytest.mark.asyncio
async def test_active_runtime_audit_reports_excluded_residual_and_plugin_controls(
    minimal_game_dir: Path,
) -> None:
    """当前运行验收只看真实运行文件问题，不按规则排除状态降级。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { category: 'カテゴリ', protocol: '\\\\TRP' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    _ = write_plugin_source_text(game_data, [], text_rules=text_rules)
    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
        plugin_source_files=game_data.writable_plugin_source_files,
    )

    summary = audit.summary_json()
    source_residual_count = summary["active_runtime_source_residual_count"]
    placeholder_risk_count = summary["active_runtime_placeholder_risk_count"]
    assert isinstance(source_residual_count, int)
    assert isinstance(placeholder_risk_count, int)
    assert source_residual_count >= 1
    assert placeholder_risk_count >= 1
    assert {issue.code for issue in audit.issues} >= {
        "active_runtime_source_residual",
        "active_runtime_placeholder_risk",
    }


@pytest.mark.asyncio
async def test_active_runtime_audit_can_limit_to_read_and_syntax_checks(
    minimal_game_dir: Path,
) -> None:
    """普通写回后验收未开启插件源码支线时，只检查启用源码文件可读和语法。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { category: 'カテゴリ', protocol: '\\\\TRP' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
        audit_text_issues=False,
    )

    assert audit.summary_json()["active_runtime_text_issue_audit_enabled"] is False
    assert audit.issue_counts["active_runtime_source_residual"] == 0
    assert audit.issue_counts["active_runtime_placeholder_risk"] == 0


@pytest.mark.asyncio
async def test_active_runtime_audit_blocks_syntax_error_for_managed_plugin_source(
    minimal_game_dir: Path,
) -> None:
    """只有 ATT-MZ 已管理的插件源码语法错误才是写后验收硬错误。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "ManagedBroken", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "ManagedBroken.js").write_text("const Messages = { title: '坏掉 };\n", encoding="utf-8")
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
        runtime_write_map_records=[
            PluginSourceRuntimeWriteMapRecord(
                location_path="js/plugins/ManagedBroken.js/ast:string:0:1:dummy",
                source_file_name="ManagedBroken.js",
                source_selector="ast:string:0:1:dummy",
                source_file_hash="source-hash",
                source_text_hash="source-text-hash",
                translation_lines_hash="translation-hash",
                runtime_file_name="ManagedBroken.js",
                runtime_selector="ast:string:0:1:dummy",
                runtime_file_hash="runtime-hash",
                runtime_text_hash="runtime-text-hash",
                runtime_line=1,
                created_at="2026-01-01T00:00:00",
            )
        ],
    )

    assert audit.issue_counts["active_runtime_syntax_error"] == 1
    assert audit.summary_json()["active_runtime_blocking_issue_count"] == 1
    assert audit.issues[0].blocking is True


@pytest.mark.asyncio
async def test_active_runtime_audit_batches_native_ast_scan(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行审计批量扫描插件源码，避免逐文件跨 Python/Rust 边界。"""
    clear_plugin_source_native_scan_cache()
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.extend(
        [
            {"name": "AuditBatchA", "status": True, "description": "", "parameters": {}},
            {"name": "AuditBatchB", "status": True, "description": "", "parameters": {}},
        ]
    )
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "AuditBatchA.js").write_text(
        "const Messages = { title: 'カテゴリA' };\n",
        encoding="utf-8",
    )
    _ = (plugin_source_dir / "AuditBatchB.js").write_text(
        "const Messages = { title: 'カテゴリB' };\n",
        encoding="utf-8",
    )
    batch_calls: list[tuple[str, ...]] = []

    def counting_batch_scan(files: dict[str, str]) -> object:
        """记录批量 AST 入口调用，并用真实解析器返回结果。"""
        batch_calls.append(tuple(sorted(files)))
        from app.native_javascript_ast import parse_native_javascript_string_spans

        return {
            file_name: parse_native_javascript_string_spans(source)
            for file_name, source in files.items()
        }

    def forbidden_single_scan(source: str) -> object:
        """当前运行审计不应逐文件调用单文件 AST 入口。"""
        _ = source
        raise AssertionError("当前运行审计不应调用单文件 AST 入口")

    monkeypatch.setattr(
        "app.plugin_source_text.scanner.parse_native_javascript_string_spans_batch",
        counting_batch_scan,
    )
    monkeypatch.setattr(
        "app.plugin_source_text.scanner.parse_native_javascript_string_spans",
        forbidden_single_scan,
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
    )

    assert len(batch_calls) == 1
    assert {"AuditBatchA.js", "AuditBatchB.js"} <= set(batch_calls[0])
    assert audit.issue_counts["active_runtime_source_residual"] >= 2


@pytest.mark.asyncio
async def test_active_runtime_audit_errors_for_unreviewed_source_candidate(
    minimal_game_dir: Path,
) -> None:
    """未审查的插件源码源语言候选仍然阻塞当前运行验收。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { title: '未審査テキスト' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    _ = write_plugin_source_text(game_data, [], text_rules=text_rules)
    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
        plugin_source_files=game_data.writable_plugin_source_files,
    )

    assert audit.issue_counts["active_runtime_source_residual"] == 1
    assert audit.issues[0].code == "active_runtime_source_residual"
    assert audit.issues[0].blocking is True
    payload = audit.issues[0].to_json_object()
    assert payload["mapping_status"] == "runtime_mapping_missing"
    assert payload["actionability"] == "review_plugin_source_rules"
    assert payload["source_review_required"] is True


@pytest.mark.asyncio
async def test_active_runtime_audit_consumes_native_literal_warning_fact(
    minimal_game_dir: Path,
) -> None:
    """运行审计必须消费 native 字符串分类，不能用 Python 源语言判定覆盖告警事实。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "NativeFacts", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    source = "const matcher = /unused/;\n"
    game_data = await load_game_data(minimal_game_dir)
    literal = plugin_source_text_scanner.PluginSourceStringLiteral(
        file_name="NativeFacts.js",
        selector="ast:string:0:1:test",
        text="未審査テキスト",
        raw_text="未審査テキスト",
        line=1,
        start_index=0,
        end_index=1,
        active=True,
        context="literal",
        literal_kind="regex_pattern",
        audit_default_severity="warning",
    )
    batch_scan = PluginSourceBatchTextScan(
        file_scans={
            "NativeFacts.js": plugin_source_text_scanner.PluginSourceFileTextScan(
                file_name="NativeFacts.js",
                file_hash=build_plugin_source_file_hash(source),
                literals=(literal,),
                candidate_index=plugin_source_text_scanner.PluginSourceCandidateIndex(candidates=(), by_selector={}),
            )
        },
        syntax_errors={},
    )
    text_rules = TextRules.from_setting(TextRulesSetting())

    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
        plugin_source_files={"NativeFacts.js": source},
        plugin_source_batch_scan=batch_scan,
    )

    issue = next(issue for issue in audit.issues if issue.code == "active_runtime_source_residual")
    assert issue.blocking is False
    payload = issue.to_json_object()
    assert payload["literal_kind"] == "regex_pattern"
    assert payload["audit_default_severity"] == "warning"
    assert payload["mapping_status"] == "runtime_mapping_missing"
    assert payload["actionability"] == "review_plugin_source_code"
    assert payload["source_review_required"] is False


@pytest.mark.asyncio
async def test_active_runtime_audit_warns_for_unmapped_regex_control_fragment(
    minimal_game_dir: Path,
) -> None:
    """未映射的源码内部正则片段只作为巡检告警，不阻断完成。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "RegexSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "RegexSource.js").write_text(
        "function unpackerMatcher() { return '\\\\w+'; }\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
    )

    issue = next(issue for issue in audit.issues if issue.code == "active_runtime_placeholder_risk")
    assert issue.fragment == "\\w"
    assert issue.blocking is False
    payload = issue.to_json_object()
    assert payload["mapping_status"] == "runtime_mapping_missing"
    assert payload["actionability"] == "review_plugin_source_code"
    assert payload["source_review_required"] is False
    assert audit.summary_json()["active_runtime_blocking_issue_count"] == 0


@pytest.mark.asyncio
async def test_active_runtime_audit_warns_for_unmapped_packer_source_residual(
    minimal_game_dir: Path,
) -> None:
    """未映射的 packer/eval 内部字符串命中源文残留时不阻断完成。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "PackerSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    packer_payload = (
        "3 e=['z','y','x','A','B','n','E','l','m','D','o','C','w','v','r','q','p'];"
        "(8(d,j){3 h=8(n){s(--n){d['u'](d['F']())}};h(++j)}(e,R));"
        "3 0=8(7,Q){7=7-5;3 o=e[7];T o};"
        "W[0('5')][0('V')][0('P')][0('O')]=8(2){"
        "1[0('I')]();3 4=1['H'];4[0('K')](4[0('L')],1[0('N')]);"
        "3 6=!!2[0('f')];3 b=6?2[0('f')]:2[0('h')];"
        "3 9=6?2[0('S')]:2[0('i')];"
        "M(9!==1['n']||b!==1[0('h')]||6){"
        "4[0('J')](4[0('U')],5,1[0('g')],1['m'],1['o'],2)"
        "}G{4[0('X')](4['l'],5,5,5,1[0('g')],1[0('t')],2)}"
        "1[0('h')]=b;1[0('i')]=9};"
    )
    _ = (plugin_source_dir / "PackerSource.js").write_text(
        f"eval({packer_payload!r});\n",
        encoding="utf-8",
    )
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="en")
    text_rules = TextRules.from_setting(setting.text_rules)
    game_data = await load_game_data(minimal_game_dir)

    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
    )

    issue = next(issue for issue in audit.issues if issue.code == "active_runtime_source_residual")
    assert issue.blocking is False
    payload = issue.to_json_object()
    assert payload["mapping_status"] == "runtime_mapping_missing"
    assert payload["actionability"] == "review_plugin_source_code"
    assert payload["source_review_required"] is False
    assert audit.summary_json()["active_runtime_blocking_issue_count"] == 0


@pytest.mark.asyncio
async def test_active_runtime_audit_reports_current_runtime_control_risk(
    minimal_game_dir: Path,
) -> None:
    """当前运行源码变化后，验收直接报告真实控制符风险。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { protocol: '\\\\TRP' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    _ = write_plugin_source_text(game_data, [], text_rules=text_rules)
    game_data.writable_plugin_source_files["HardcodedText.js"] = "const Messages = { protocol: '\\\\ii[1]' };\n"
    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
        plugin_source_files=game_data.writable_plugin_source_files,
    )

    assert audit.issue_counts["active_runtime_placeholder_risk"] == 1
    issue = next(issue for issue in audit.issues if issue.code == "active_runtime_placeholder_risk")
    assert issue.fragment == "\\ii[1]"


@pytest.mark.asyncio
async def test_active_runtime_control_risk_uses_native_literal_facts(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行源码控制符风险必须消费 Rust fact，不能回到 Python 文本规则扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "NativeControlFacts", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "NativeControlFacts.js").write_text(
        "const Messages = { protocol: '\\\\ii[1]' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    def forbidden_python_control_scan(self: TextRules, text: str) -> NoReturn:
        """active runtime 不能调用 Python 控制符候选扫描。"""
        _ = (self, text)
        raise AssertionError("active runtime must use native literal facts")

    monkeypatch.setattr(
        TextRules,
        "iter_unprotected_control_sequence_candidates",
        forbidden_python_control_scan,
    )

    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
    )

    assert audit.issue_counts["active_runtime_placeholder_risk"] == 1
    issue = next(issue for issue in audit.issues if issue.code == "active_runtime_placeholder_risk")
    assert issue.fragment == "\\ii[1]"


@pytest.mark.asyncio
async def test_active_runtime_audit_requires_native_literal_facts_for_classification(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行源码审计缺少 Rust literal fact 时必须显式失败，不能用 Python 侧分类继续跑。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "MissingNativeFact", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "MissingNativeFact.js").write_text(
        "const Messages = { title: '未審査テキスト' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)

    def missing_native_facts(
        *,
        literals: Mapping[str, NativeRuntimeLiteralIssueInput],
        text_rules: TextRules,
    ) -> dict[str, NativeRuntimeLiteralIssueFact]:
        _ = (literals, text_rules)
        return {}

    monkeypatch.setattr(
        plugin_source_runtime_audit,
        "collect_native_runtime_literal_issue_facts",
        missing_native_facts,
    )

    with pytest.raises(RuntimeError, match="Rust runtime literal fact 缺失"):
        _ = audit_active_runtime_plugin_source(
            game_data=game_data,
            text_rules=text_rules,
        )


@pytest.mark.asyncio
async def test_active_runtime_audit_blocks_mapped_translated_control_risk(
    minimal_game_dir: Path,
) -> None:
    """已由 ATT-MZ 写入映射覆盖的译文控制符风险仍然阻断。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "MappedRisk", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source = "const Messages = { protocol: '\\\\ii[1]' };\n"
    _ = (plugin_source_dir / "MappedRisk.js").write_text(source, encoding="utf-8")
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    runtime_literal = iter_plugin_source_string_literals(
        file_name="MappedRisk.js",
        source=source,
        active=True,
    )[0]

    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
        runtime_write_map_records=[
            PluginSourceRuntimeWriteMapRecord(
                mapping_kind="translated",
                location_path=f"js/plugins/MappedRisk.js/{runtime_literal.selector}",
                source_file_name="MappedRisk.js",
                source_selector=runtime_literal.selector,
                source_file_hash=build_plugin_source_file_hash(source),
                source_text_hash=plugin_source_runtime_hash_text(runtime_literal.text),
                translation_lines_hash=plugin_source_runtime_hash_lines([runtime_literal.text]),
                runtime_file_name="MappedRisk.js",
                runtime_selector=runtime_literal.selector,
                runtime_file_hash=build_plugin_source_file_hash(source),
                runtime_text_hash=plugin_source_runtime_hash_text(runtime_literal.text),
                runtime_line=runtime_literal.line,
                created_at="2026-06-07T00:00:00",
            )
        ],
    )

    issue = next(issue for issue in audit.issues if issue.code == "active_runtime_placeholder_risk")
    assert issue.blocking is True
    payload = issue.to_json_object()
    assert payload["mapping_status"] == "mapped_translate"
    assert payload["actionability"] == "fix_translation"
    assert payload["source_review_required"] is False


@pytest.mark.asyncio
async def test_plugin_source_rules_reject_selector_included_and_excluded(
    minimal_game_dir: Path,
) -> None:
    """同一插件源码 selector 不能同时标记为翻译和排除。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { title: '翻訳する本文' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    candidate = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates[0]
    rule_text = json.dumps(
        [
            {
                "file": "HardcodedText.js",
                "selectors": [candidate.selector],
                "excluded_selectors": [candidate.selector],
            }
        ],
        ensure_ascii=False,
    )

    with pytest.raises(ValueError, match="不能同时"):
        _ = build_plugin_source_rule_records_from_import(
            game_data=game_data,
            import_file=parse_plugin_source_rule_import_text(rule_text),
            text_rules=text_rules,
        )


@pytest.mark.asyncio
async def test_plugin_source_write_back_requires_native_ast(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码写回阶段没有原生 AST 解析器时必须停止。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { title: 'プラグイン直書き' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    candidate = next(
        candidate
        for candidate in build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates
        if candidate.text == "プラグイン直書き"
    )
    records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(
            json.dumps([{"file": "HardcodedText.js", "selectors": [candidate.selector]}], ensure_ascii=False)
        ),
        text_rules=text_rules,
    )
    item = PluginSourceTextExtraction(game_data, records, text_rules).extract_all_text()[
        "js/plugins/HardcodedText.js"
    ].translation_items[0]
    item.translation_lines = ["插件直写"]

    def missing_native_module() -> object:
        """模拟发行包或开发环境缺少 Rust 原生扩展。"""
        raise RuntimeError("Rust 原生扩展不可用")

    monkeypatch.setattr("app.native_write_plan._load_native_module", missing_native_module)

    _create_test_source_snapshot(game_data)
    with pytest.raises(ValueError, match="Rust 原生扩展不可用"):
        _ = write_plugin_source_text(
            game_data,
            [item],
            text_rules=text_rules,
        )


@pytest.mark.asyncio
async def test_plugin_source_partial_backup_keeps_unmodified_files_visible(minimal_game_dir: Path) -> None:
    """插件源码只备份改动文件后，再次加载仍能看到未改动直接源码文件。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.extend(
        [
            {"name": "SourceA", "status": True, "description": "", "parameters": {}},
            {"name": "SourceB", "status": True, "description": "", "parameters": {}},
        ]
    )
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "SourceA.js").write_text(
        "const Messages = { title: '一つ目の本文' };\n",
        encoding="utf-8",
    )
    _ = (plugin_source_dir / "SourceB.js").write_text(
        "const Messages = { title: '二つ目の本文' };\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    candidate = next(item for item in scan.candidates if item.file_name == "SourceA.js")
    rule_text = json.dumps([{"file": "SourceA.js", "selectors": [candidate.selector]}], ensure_ascii=False)
    records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(rule_text),
        text_rules=text_rules,
    )
    item = PluginSourceTextExtraction(game_data, records, text_rules).extract_all_text()[
        "js/plugins/SourceA.js"
    ].translation_items[0]
    item.translation_lines = ["第一个正文"]

    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    _ = write_plugin_source_text(
        game_data,
        [item],
        text_rules=text_rules,
    )
    write_game_files(game_data)
    reloaded = await load_game_data(minimal_game_dir)

    assert {"SourceA.js", "SourceB.js"}.issubset(reloaded.plugin_source_files)
    assert "一つ目の本文" in reloaded.plugin_source_files["SourceA.js"]
    assert "二つ目の本文" in reloaded.plugin_source_files["SourceB.js"]


@pytest.mark.asyncio
async def test_plugin_source_loader_splits_translation_source_and_active_runtime(
    minimal_game_dir: Path,
) -> None:
    """翻译源视图读取 origin，当前运行视图读取真实激活源码。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "SourceA", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    origin_source_dir = minimal_game_dir / "js" / "plugins_source_origin"
    origin_source_dir.mkdir()
    _ = (plugin_source_dir / "SourceA.js").write_text(
        "const Messages = { title: '当前运行文本' };\n",
        encoding="utf-8",
    )
    _ = (origin_source_dir / "SourceA.js").write_text(
        "const Messages = { title: '原始翻译源' };\n",
        encoding="utf-8",
    )

    translation_source = await load_game_data(minimal_game_dir)
    active_runtime = await load_active_game_data(
        minimal_game_dir,
        include_plugin_source_files=True,
    )

    assert "原始翻译源" in translation_source.plugin_source_files["SourceA.js"]
    assert "当前运行文本" in active_runtime.plugin_source_files["SourceA.js"]


@pytest.mark.asyncio
async def test_export_plugin_source_ast_map_view_selects_translation_source_or_active_runtime(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """AST 地图命令必须显式按视图导出 origin 或当前运行源码。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "SourceA", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source_path = plugin_source_dir / "SourceA.js"
    _ = source_path.write_text(
        "const Messages = { title: '原始ソース' };\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _ = source_path.write_text(
        "const Messages = { title: '現在実行中' };\n",
        encoding="utf-8",
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    translation_source_path = tmp_path / "translation-source.json"
    active_runtime_path = tmp_path / "active-runtime.json"

    translation_source_report = await service.export_plugin_source_ast_map(
        game_title="テストゲーム",
        output_path=translation_source_path,
        source_view="translation-source",
    )
    active_runtime_report = await service.export_plugin_source_ast_map(
        game_title="テストゲーム",
        output_path=active_runtime_path,
        source_view="active-runtime",
    )
    translation_source_payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(translation_source_path.read_text(encoding="utf-8")))),
        "translation-source AST",
    )
    active_runtime_payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(active_runtime_path.read_text(encoding="utf-8")))),
        "active-runtime AST",
    )

    assert translation_source_report.summary["source_view"] == "translation-source"
    assert active_runtime_report.summary["source_view"] == "active-runtime"
    assert translation_source_payload["source_view"] == "translation-source"
    assert active_runtime_payload["source_view"] == "active-runtime"
    assert "原始ソース" in json.dumps(translation_source_payload, ensure_ascii=False)
    assert "現在実行中" in json.dumps(active_runtime_payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_plugin_source_high_risk_pauses_workflow_until_rules_are_confirmed(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """显式插件源码风险扫描为高风险且没有规则时，正文流程必须停止。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append(
        {
            "name": "HighRiskSource",
            "status": True,
            "description": "",
            "parameters": {},
        }
    )
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HighRiskSource.js").write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('高リスク{i}', 0, 0, 320);"
            for i in range(301)
        ),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_external_workflow_reviews(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        game_data = await load_game_data(session.game_path)
        session.set_game_data(game_data)
        text_rules = TextRules.from_setting(setting.text_rules)
        plugin_source_scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )

        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
            plugin_source_scan=plugin_source_scan,
        )

    assert errors
    assert errors[0].code == "plugin_source_text_high_risk"
    assert "插件源码" in errors[0].message


@pytest.mark.asyncio
async def test_plugin_source_stale_rule_hash_blocks_workflow(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行插件源码变化不能污染翻译源规则身份。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HighRiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source_path = plugin_source_dir / "HighRiskSource.js"
    _ = source_path.write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('高リスク{i}', 0, 0, 320);"
            for i in range(301)
        ),
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    initial_game_data = await load_game_data(minimal_game_dir)
    candidate = build_native_plugin_source_scan(
        game_data=initial_game_data,
        text_rules=text_rules,
    ).candidates[0]
    records = build_plugin_source_rule_records_from_import(
        game_data=initial_game_data,
        import_file=parse_plugin_source_rule_import_text(
            json.dumps([{"file": "HighRiskSource.js", "selectors": [candidate.selector]}], ensure_ascii=False)
        ),
        text_rules=text_rules,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_source_text_rules(records)

    _ = source_path.write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('変更後高リスク{i}', 0, 0, 320);"
            for i in range(301)
        ),
        encoding="utf-8",
    )
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        changed_game_data = await load_game_data(session.game_path)
        session.set_game_data(changed_game_data)
        scope = await TextScopeService().build(
            session=session,
            game_data=changed_game_data,
            text_rules=text_rules,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=changed_game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert not any(error.code == "stale_plugin_source_rules" for error in errors)


@pytest.mark.asyncio
async def test_prepare_workspace_writes_plugin_source_risk_summary_without_ast_map(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 Agent 工作区用 Rust 事实写插件源码风险摘要，不提前写完整 AST 候选地图。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "RiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "RiskSource.js").write_text(
        "Window_Base.prototype.drawText('风险候选', 0, 0, 320);\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    workspace = tmp_path / "workspace"

    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )

    def forbidden_legacy_risk_report_json(scan: PluginSourceScan) -> JsonObject:
        """风险报告必须来自 Rust 候选事实，不能从旧 PluginSourceScan 渲染。"""
        _ = scan
        raise AssertionError("prepare-agent-workspace 不应从旧 PluginSourceScan 渲染插件源码风险报告")

    native_scan_count = 0

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    monkeypatch.setattr(PluginSourceScan, "risk_report_json", forbidden_legacy_risk_report_json)
    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )

    report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    prepare_native_scan_count = native_scan_count
    validation_report = await service.validate_agent_workspace(
        game_title="テストゲーム",
        workspace=workspace,
    )
    payload = ensure_json_object(
        coerce_json_value(
            cast(
                object,
                json.loads((workspace / "plugin-source-risk-report.json").read_text(encoding="utf-8")),
            )
        ),
        "plugin-source-risk-report.json",
    )

    assert prepare_native_scan_count == 1
    assert "risk" in payload
    assert "candidate_count" in payload
    assert payload["candidate_count"] == 1
    assert payload["active_candidate_count"] == 1
    assert "files" not in payload
    assert "candidates" not in payload
    risk = ensure_json_object(payload["risk"], "plugin-source-risk-report.risk")
    syntax_errors = ensure_json_array(payload["syntax_errors"], "plugin-source-risk-report.syntax_errors")
    assert report.summary["plugin_source_candidate_count"] == payload["candidate_count"]
    assert report.summary["plugin_source_high_risk"] == risk["high_risk"]
    assert report.summary["plugin_source_syntax_error_file_count"] == len(syntax_errors)
    assert not (workspace / "plugin-source-rules.json").exists()
    assert "plugin_source_rules_missing" not in {error.code for error in validation_report.errors}


@pytest.mark.asyncio
async def test_prepare_workspace_warns_and_skips_invalid_plugin_source(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """原游戏混入非法 JS 插件源码时，工作区准备只告警并跳过源码扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "BrokenSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "BrokenSource.js").write_text("=begin\nRGSS script\n", encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    workspace = tmp_path / "workspace"

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    payload = ensure_json_object(
        coerce_json_value(
            cast(
                object,
                json.loads((workspace / "plugin-source-risk-report.json").read_text(encoding="utf-8")),
            )
        ),
        "plugin-source-risk-report.json",
    )

    assert report.status == "warning"
    assert {warning.code for warning in report.warnings} >= {"plugin_source_syntax_warning"}
    assert report.summary["plugin_source_syntax_error_file_count"] == 1
    assert ensure_json_array(payload["syntax_errors"], "plugin-source-risk-report.syntax_errors") == [
        {
            "file": "BrokenSource.js",
            "active": True,
            "syntax_error": "原生 AST 解析报告 JS 语法错误",
        }
    ]


@pytest.mark.asyncio
async def test_quality_report_hides_plugin_source_review_fields_until_branch_started(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """低风险且未启动支线时，质量报告不暴露插件源码审查状态。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "RiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "RiskSource.js").write_text(
        "Window_Base.prototype.drawText('风险候选', 0, 0, 320);\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).quality_report(game_title="テストゲーム")

    assert "plugin_source_unreviewed_count" not in report.summary
    assert "plugin_source_unreviewed_candidates" not in report.details


@pytest.mark.asyncio
async def test_export_plugin_source_ast_map_report_keeps_full_map_only_in_output_file(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """AST 地图导出命令的 JSON 报告不能把完整候选地图再写到 stdout。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "RiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "RiskSource.js").write_text(
        "const Messages = { title: '风险候选' };\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    output_path = tmp_path / "plugin-source-ast-map.json"

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).export_plugin_source_ast_map(
        game_title="テストゲーム",
        output_path=output_path,
    )
    payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(output_path.read_text(encoding="utf-8")))),
        "plugin-source-ast-map.json",
    )

    assert report.status == "ok"
    assert report.summary["candidate_count"] == 1
    assert "files" in payload
    assert "candidates" not in payload
    files = ensure_json_array(payload["files"], "plugin-source-ast-map.files")
    first_file = ensure_json_object(files[0], "plugin-source-ast-map.files[0]")
    assert "candidates" in first_file
    assert "files" not in report.details
    assert "candidates" not in report.details
    assert report.details["output"] == str(output_path)


@pytest.mark.asyncio
async def test_export_plugin_source_ast_map_uses_native_candidate_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AST 地图导出命令必须消费 Rust 候选入口，不再走 Python AST 主扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "NativeAstSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "NativeAstSource.js").write_text(
        "\n".join(
            [
                "const Messages = { title: '原生候補', label: '\\u77ED\\u3044' };",
                "Window_Base.prototype.drawText('強い文脈', 0, 0, 320);",
            ]
        ),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    output_path = tmp_path / "plugin-source-ast-map.json"

    native_scan_count = 0

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).export_plugin_source_ast_map(
        game_title="テストゲーム",
        output_path=output_path,
    )
    payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(output_path.read_text(encoding="utf-8")))),
        "plugin-source-ast-map.json",
    )
    files = ensure_json_array(payload["files"], "plugin-source-ast-map.files")
    native_file = next(
        ensure_json_object(file_payload, "plugin-source-ast-map.files[]")
        for file_payload in files
        if ensure_json_object(file_payload, "plugin-source-ast-map.files[]").get("file") == "NativeAstSource.js"
    )
    candidates = ensure_json_array(native_file["candidates"], "plugin-source-ast-map.files[].candidates")
    first_candidate = ensure_json_object(candidates[0], "plugin-source-ast-map.files[].candidates[0]")

    assert report.status == "ok"
    assert native_scan_count == 1
    assert payload["candidate_count"] == 3
    assert "active_candidate_count" not in payload
    assert "candidates" not in payload
    assert payload["source_view"] == "translation-source"
    assert native_file["active"] is True
    assert native_file["strong_context_text_count"] == 3
    assert native_file["file_score"] == 9
    assert isinstance(native_file["file_hash"], str)
    assert set(first_candidate) == {
        "file",
        "line",
        "selector",
        "text",
        "context",
        "api",
        "key",
        "ast_context",
        "active",
        "confidence",
        "structural_flags",
    }
    assert first_candidate["file"] == "NativeAstSource.js"
    assert isinstance(first_candidate["line"], int)
    assert str(first_candidate["selector"]).startswith("ast:string:")
    assert first_candidate["active"] is True
    assert ensure_json_object(first_candidate["ast_context"], "candidate.ast_context")
    assert {
        "raw_text",
        "quote",
        "start_index",
        "end_index",
        "content_start_index",
        "content_end_index",
        "source_file",
        "file_hash",
        "domain",
        "location_path",
        "rule_key",
        "original_text",
    }.isdisjoint(first_candidate)
    assert "files" not in report.summary
    assert "candidates" not in report.summary
    assert "active_candidate_count" not in report.summary
    assert "files" not in report.details
    assert "candidates" not in report.details
    assert report.details["output"] == str(output_path)


@pytest.mark.asyncio
async def test_scan_plugin_source_text_uses_native_candidate_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码风险扫描命令必须消费 Rust 候选入口，不再走 Python AST 主扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "NativeScanSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "NativeScanSource.js").write_text(
        "\n".join(
            [
                "const Messages = { title: '原生候选', label: '\\u77ED\\u3044' };",
                "Window_Base.prototype.drawText('強い文脈', 0, 0, 320);",
            ]
        ),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    output_path = tmp_path / "plugin-source-risk-report.json"

    native_scan_count = 0

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).scan_plugin_source_text(
        game_title="テストゲーム",
        output_path=output_path,
    )
    payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(output_path.read_text(encoding="utf-8")))),
        "plugin-source-risk-report.json",
    )
    risk = ensure_json_object(payload["risk"], "plugin-source-risk-report.risk")

    assert report.status == "ok"
    assert native_scan_count == 1
    assert payload["candidate_count"] == 3
    assert payload["active_candidate_count"] == 3
    assert payload["syntax_errors"] == []
    assert payload["source_view"] == "translation-source"
    assert risk["strong_context_text_count"] == 3
    assert risk["risk_score"] == 9
    assert report.summary["candidate_count"] == 3
    assert report.summary["strong_context_text_count"] == 3
    for container in (payload, report.summary, report.details):
        assert "files" not in container
        assert "candidates" not in container


@pytest.mark.asyncio
async def test_scan_plugin_source_text_keeps_python_only_source_pattern_contract(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """source_text_required_pattern 只承诺 Python re，命令不能把它升级成 Rust regex 约束。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "PythonRegexSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "PythonRegexSource.js").write_text(
        "Window_Base.prototype.drawText('原生候选', 0, 0, 320);\n",
        encoding="utf-8",
    )
    base_setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    custom_setting = base_setting.model_copy(
        update={
            "text_rules": base_setting.text_rules.model_copy(
                update={"source_text_required_pattern": "(?<=原)生"}
            )
        }
    )

    def fake_load_setting(*args: object, **kwargs: object) -> Setting:
        _ = (args, kwargs)
        return custom_setting

    monkeypatch.setattr("app.agent_toolkit.services.workspace.load_setting", fake_load_setting)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    output_path = tmp_path / "plugin-source-risk-report.json"

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).scan_plugin_source_text(
        game_title="テストゲーム",
        output_path=output_path,
    )
    payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(output_path.read_text(encoding="utf-8")))),
        "plugin-source-risk-report.json",
    )

    assert report.status == "ok"
    assert payload["candidate_count"] == 1
    assert payload["active_candidate_count"] == 1


@pytest.mark.asyncio
async def test_scan_plugin_source_text_handles_empty_plugin_source_files(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码风险扫描没有直接源码文件时仍输出空风险报告。"""
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    for source_path in plugin_source_dir.iterdir():
        if source_path.is_file():
            source_path.unlink()
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    output_path = tmp_path / "plugin-source-risk-report.json"

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).scan_plugin_source_text(
        game_title="テストゲーム",
        output_path=output_path,
    )
    payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(output_path.read_text(encoding="utf-8")))),
        "plugin-source-risk-report.json",
    )
    risk = ensure_json_object(payload["risk"], "plugin-source-risk-report.risk")

    assert report.status == "warning"
    assert {warning.code for warning in report.warnings} == {"plugin_source_text_empty"}
    assert payload["candidate_count"] == 0
    assert payload["active_candidate_count"] == 0
    assert payload["syntax_errors"] == []
    assert risk["risk_score"] == 0
    assert risk["scanned_file_count"] == 0
    assert risk["ignored_file_count"] == 0


@pytest.mark.asyncio
async def test_plugin_source_rule_validation_rejects_invalid_js_directly(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码无法通过 JS AST 解析时，规则校验直接失败。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "BrokenSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "BrokenSource.js").write_text(
        "const Messages = { title: '壊れた本文',\n",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    rule_text = json.dumps(
        [{"file": "BrokenSource.js", "selectors": ["ast:string:0:1:invalid"]}],
        ensure_ascii=False,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")

    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)

    assert scan.syntax_errors == {"BrokenSource.js": "原生 AST 解析报告 JS 语法错误"}
    assert scan.risk.syntax_error_file_count == 1

    validation_report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).validate_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=rule_text,
    )

    assert validation_report.status == "error"
    assert validation_report.summary["unwritable_count"] == 0
    assert validation_report.errors[0].code == "plugin_source_rules_invalid"
    assert "JS AST 解析" in validation_report.errors[0].message
    assert validation_report.details["rules"] == []


@pytest.mark.asyncio
async def test_quality_report_consumes_text_index_plugin_source_review_incomplete(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告只消费索引，并保留冷索引发现的插件源码未归类错误。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HighRiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HighRiskSource.js").write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('高リスク{i}', 0, 0, 320);"
            for i in range(301)
        ),
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    first_candidate = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates[0]
    records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(
            json.dumps(
                [
                    {
                        "file": "HighRiskSource.js",
                        "selectors": [first_candidate.selector],
                        "excluded_selectors": [],
                    }
                ],
                ensure_ascii=False,
            )
        ),
        text_rules=text_rules,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_source_text_rules(records)
    await _install_minimal_external_workflow_reviews(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).quality_report(game_title="テストゲーム")

    assert report.status == "error"
    error_codes = {error.code for error in report.errors}
    assert "plugin_source_review_incomplete" in error_codes
    assert "coverage_missing_translation" not in error_codes


@pytest.mark.asyncio
async def test_validate_plugin_source_rules_errors_when_review_is_incomplete(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码规则没有覆盖全部候选时，校验命令必须报 error。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "TwoCandidates", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "TwoCandidates.js").write_text(
        "\n".join(
            [
                "Window_Base.prototype.drawText('候補一つ目', 0, 0, 320);",
                "Window_Base.prototype.drawText('候補二つ目', 0, 0, 320);",
            ]
        ),
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    first_candidate = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates[0]
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).validate_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "TwoCandidates.js",
                    "selectors": [first_candidate.selector],
                    "excluded_selectors": [],
                }
            ],
            ensure_ascii=False,
        ),
    )

    assert report.status == "error"
    assert "plugin_source_review_incomplete" in {error.code for error in report.errors}
    assert report.summary["unreviewed_selector_count"] == 1


@pytest.mark.asyncio
async def test_validate_plugin_source_rules_uses_prefix_read_for_translated_count(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码规则校验只读取插件源码前缀内的已保存译文。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "OneCandidateSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "OneCandidateSource.js").write_text(
        "Window_Base.prototype.drawText('候補一つ目', 0, 0, 320);",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    selectors_by_file: dict[str, list[str]] = {}
    for candidate in scan.candidates:
        selectors_by_file.setdefault(candidate.file_name, []).append(candidate.selector)
    rules_payload = [
        {
            "file": file_name,
            "selectors": selectors,
            "excluded_selectors": [],
        }
        for file_name, selectors in sorted(selectors_by_file.items())
    ]
    records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(json.dumps(rules_payload, ensure_ascii=False)),
        text_rules=text_rules,
        scan=scan,
    )
    extracted_map = PluginSourceTextExtraction(
        game_data,
        rule_records=records,
        text_rules=text_rules,
        scan=scan,
    ).extract_all_text()
    target_item = next(
        item
        for translation_data in extracted_map.values()
        for item in translation_data.translation_items
        if item.location_path.startswith("js/plugins/OneCandidateSource.js/")
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=target_item.location_path,
                    item_type=target_item.item_type,
                    original_lines=target_item.original_lines,
                    translation_lines=["候选一"],
                ),
                TranslationItem(
                    location_path="Actors.json/1/name",
                    item_type="short_text",
                    original_lines=["関係ない名前"],
                    translation_lines=["无关名字"],
                ),
            ]
        )

    async def forbidden_full_path_read(_self: TargetGameSession) -> set[str]:
        raise AssertionError("插件源码规则校验不能全量读取已保存路径")

    monkeypatch.setattr(TargetGameSession, "read_translation_location_paths", forbidden_full_path_read)

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).validate_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(rules_payload, ensure_ascii=False),
    )

    assert report.status == "ok"
    assert report.summary["translated_count"] == 1


@pytest.mark.asyncio
async def test_validate_plugin_source_rules_uses_native_plugin_source_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """独立插件源码规则校验用 Rust 候选事实，不回到旧 Python 主扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "NativeValidateRule", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "NativeValidateRule.js").write_text(
        "Window_Base.prototype.drawText('単独校験候補', 0, 0, 320);",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    candidate = next(candidate for candidate in scan.candidates if candidate.file_name == "NativeValidateRule.js")
    rules_text = json.dumps(
        [
            {
                "file": "NativeValidateRule.js",
                "selectors": [candidate.selector],
                "excluded_selectors": [],
            }
        ],
        ensure_ascii=False,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    native_scan_count = 0

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    def forbidden_legacy_plugin_source_scan(*args: object, **kwargs: object) -> PluginSourceScan:
        _ = (args, kwargs)
        raise AssertionError("validate-plugin-source-rules 不应调用旧 Python 插件源码主扫描")

    def forbidden_write_probe_plugin_source_scan(
        *,
        files: dict[str, str],
        active_file_names: frozenset[str],
        text_rules: TextRules | None,
    ) -> PluginSourceBatchTextScan:
        _ = (files, active_file_names, text_rules)
        raise AssertionError("validate-plugin-source-rules 写回探针不应二次扫描插件源码 AST")

    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.rule_validation.build_plugin_source_scan",
        forbidden_legacy_plugin_source_scan,
        raising=False,
    )
    monkeypatch.setattr(
        "app.text_scope.write_probe.scan_plugin_source_files_text_strict",
        forbidden_write_probe_plugin_source_scan,
        raising=False,
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).validate_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    assert native_scan_count == 1
    assert report.status == "ok"
    assert report.summary["hit_count"] == 1


@pytest.mark.asyncio
async def test_import_plugin_source_rules_rejects_high_risk_empty_review(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """高风险插件源码不能通过空规则确认绕过源码候选审查。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HighRiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HighRiskSource.js").write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('高リスク{i}', 0, 0, 320);"
            for i in range(301)
        ),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).import_plugin_source_rules(
        game_title="テストゲーム",
        rules_text="[]",
        confirm_empty=True,
    )

    assert report.status == "error"
    assert "plugin_source_review_incomplete" in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_import_plugin_source_rules_uses_native_plugin_source_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码规则导入用 Rust 候选事实，不回到旧 Python 主扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "NativeImportRule", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "NativeImportRule.js").write_text(
        "Window_Base.prototype.drawText('導入校験候補', 0, 0, 320);",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    candidate = next(candidate for candidate in scan.candidates if candidate.file_name == "NativeImportRule.js")
    rules_text = json.dumps(
        [
            {
                "file": "NativeImportRule.js",
                "selectors": [candidate.selector],
                "excluded_selectors": [],
            }
        ],
        ensure_ascii=False,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    native_scan_count = 0

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    def forbidden_legacy_plugin_source_scan(*args: object, **kwargs: object) -> PluginSourceScan:
        _ = (args, kwargs)
        raise AssertionError("import-plugin-source-rules 不应调用旧 Python 插件源码主扫描")

    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.rule_validation.build_plugin_source_scan",
        forbidden_legacy_plugin_source_scan,
        raising=False,
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).import_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    assert native_scan_count == 1
    assert report.status == "ok"
    assert report.summary["selector_count"] == 1
    assert report.summary["deleted_translation_items"] == 0
    async with await registry.open_game("テストゲーム") as session:
        stored_rules = await session.read_plugin_source_text_rules()

    assert len(stored_rules) == 1
    assert stored_rules[0].file_name == "NativeImportRule.js"
    assert stored_rules[0].selectors == [candidate.selector]


@pytest.mark.asyncio
async def test_import_plugin_source_rules_replaces_stale_existing_rule(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """旧插件源码规则过期时，仍然可以导入新规则并清理旧译文。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { title: 'プラグイン直書き' };\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    candidate = next(
        candidate
        for candidate in build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates
        if candidate.file_name == "HardcodedText.js"
    )
    stale_item = TranslationItem(
        location_path="js/plugins/HardcodedText.js/stale-selector",
        item_type="short_text",
        original_lines=["古いプラグイン"],
        translation_lines=["旧插件"],
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="HardcodedText.js",
                    file_hash="stale-hash",
                    selectors=["stale-selector"],
                )
            ]
        )
        await session.write_translation_items([stale_item])

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).import_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "HardcodedText.js",
                    "selectors": [candidate.selector],
                    "excluded_selectors": [],
                }
            ],
            ensure_ascii=False,
        ),
    )

    async with await registry.open_game("テストゲーム") as session:
        rules = await session.read_plugin_source_text_rules()
        paths = await session.read_translation_location_paths()

    assert report.status == "warning"
    assert report.summary["deleted_translation_items"] == 1
    assert [rule.selectors for rule in rules] == [[candidate.selector]]
    assert stale_item.location_path not in paths


@pytest.mark.asyncio
async def test_quality_report_does_not_discover_plugin_source_before_branch_started(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未启动插件源码支线时，质量报告不得隐藏扫描插件源码目录。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "HighRiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HighRiskSource.js").write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('高リスク{i}', 0, 0, 320);"
            for i in range(301)
        ),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_external_workflow_reviews(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    native_scan_count = 0

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    _forbid_legacy_plugin_source_scan(monkeypatch)
    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).quality_report(game_title="テストゲーム")

    assert native_scan_count == 0
    assert report.status == "error"
    assert "plugin_source_text_high_risk" not in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_quality_report_write_probe_does_not_discover_plugin_source_high_risk_gate(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回级质量报告执行写回 gate，但不把插件源码发现混进热路径。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "WriteProbeHighRiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "WriteProbeHighRiskSource.js").write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('回写高リスク{i}', 0, 0, 320);"
            for i in range(301)
        ),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_external_workflow_reviews(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    native_scan_count = 0

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    _forbid_legacy_plugin_source_scan(monkeypatch)
    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).quality_report(game_title="テストゲーム", include_write_probe=True)

    assert native_scan_count == 0
    assert report.status == "error"
    assert "plugin_source_text_high_risk" not in {error.code for error in report.errors}
    assert report.summary["write_back_probe_requested"] is True
    assert report.summary["write_back_probe_executed"] is True
    assert report.summary["write_back_probe_mode"] == "rust_write_gate"


@pytest.mark.asyncio
async def test_quality_report_write_probe_reuses_plugin_source_scan_for_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回级质量报告复用插件源码审查扫描结果构建文本范围。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "QualityReuseSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "QualityReuseSource.js").write_text(
        "Window_Base.prototype.drawText('品質レポート候補', 0, 0, 320);",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    selectors_by_file: dict[str, list[str]] = {}
    for candidate in scan.candidates:
        selectors_by_file.setdefault(candidate.file_name, []).append(candidate.selector)
    records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(
            json.dumps(
                [
                    {
                        "file": file_name,
                        "selectors": selectors,
                        "excluded_selectors": [],
                    }
                    for file_name, selectors in sorted(selectors_by_file.items())
                ],
                ensure_ascii=False,
            )
        ),
        text_rules=text_rules,
        scan=scan,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_source_text_rules(records)
    await _install_minimal_external_workflow_reviews(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    _forbid_legacy_plugin_source_scan(monkeypatch)

    def forbidden_write_probe_plugin_source_scan(
        *,
        files: dict[str, str],
        active_file_names: frozenset[str],
        text_rules: TextRules | None,
    ) -> PluginSourceBatchTextScan:
        _ = (files, active_file_names, text_rules)
        raise AssertionError("quality-report 写回探针不应二次扫描插件源码 AST")

    monkeypatch.setattr(
        "app.text_scope.write_probe.scan_plugin_source_files_text_strict",
        forbidden_write_probe_plugin_source_scan,
        raising=False,
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).quality_report(game_title="テストゲーム", include_write_probe=True)

    assert report.summary["plugin_source_review_status"] == "prechecked_from_text_index"
    assert "plugin_source_reviewed_selector_count" not in report.summary
    assert "plugin_source_unreviewed_count" not in report.summary


@pytest.mark.asyncio
async def test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """通用 TextScope fallback 使用 Rust-derived scan，不回旧 Python 主扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.append({"name": "ScopeNativeFallback", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "ScopeNativeFallback.js").write_text(
        "Window_Base.prototype.drawText('範囲候補', 0, 0, 320);",
        encoding="utf-8",
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    game_data = await load_game_data(minimal_game_dir)
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    file_scan = next(item for item in scan.files if item.file_name == "ScopeNativeFallback.js")
    candidate = next(item for item in scan.candidates if item.file_name == "ScopeNativeFallback.js")
    records = [
        PluginSourceTextRuleRecord(
            file_name="ScopeNativeFallback.js",
            file_hash=file_scan.file_hash,
            selectors=[candidate.selector],
            excluded_selectors=[],
        )
    ]
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _forbid_legacy_plugin_source_scan(monkeypatch)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_source_text_rules(records)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
            include_write_probe=True,
        )

    assert plugin_source_location_path(file_name="ScopeNativeFallback.js", selector=candidate.selector) in scope.active_paths
    assert not scope.write_back_probe_error


@pytest.mark.asyncio
async def test_plugin_source_write_probe_uses_batch_preview(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码写回预演成功路径必须按文件批量扫描，避免逐条重复解析 JS。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins = ensure_json_array(_read_test_json_from_plugins_js(plugins_path), "plugins")
    plugins.extend(
        [
            {"name": "HardcodedText", "status": True, "description": "", "parameters": {}},
            {"name": "HardcodedTextExtra", "status": True, "description": "", "parameters": {}},
        ]
    )
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    sources = {
        "HardcodedText.js": "\n".join(
            f"Window_Base.prototype.drawText('探针原文{index}', 0, 0, 320);"
            for index in range(2)
        ),
        "HardcodedTextExtra.js": "Window_Base.prototype.drawText('额外探针原文', 0, 0, 320);",
    }
    for file_name, source in sources.items():
        _ = (plugin_source_dir / file_name).write_text(source, encoding="utf-8")
    loaded_sources = {
        file_name: (plugin_source_dir / file_name).read_bytes().decode("utf-8")
        for file_name in sources
    }
    game_data = await load_game_data(minimal_game_dir)
    from app.plugin_source_text.scanner import (
        scan_plugin_source_runtime_files_text_strict as real_runtime_batch_scan,
    )

    items: list[TranslationItem] = []
    setup_batch_scan = real_runtime_batch_scan(
        files=loaded_sources,
        active_file_names=frozenset(loaded_sources),
    )
    for file_name in sorted(loaded_sources):
        literals = list(setup_batch_scan.file_scans[file_name].literals)
        items.extend(
            TranslationItem(
                location_path=f"js/plugins/{file_name}/{literal.selector}",
                item_type="short_text",
                original_lines=[literal.text],
                source_line_paths=[f"js/plugins/{file_name}/{literal.selector}"],
                translation_lines=[f"探针译文{index}"],
            )
            for index, literal in enumerate(literals)
        )
    scanned_batches: list[tuple[str, ...]] = []

    def successful_native_probe(
        *,
        game_data: JsonValue,
        plugins_js: list[JsonValue],
        items: list[TranslationItem],
    ) -> list[JsonValue]:
        """模拟普通写入协议探针通过。"""
        _ = (game_data, plugins_js, items)
        return []

    def counting_plugin_source_runtime_batch_scan(
        *,
        files: dict[str, str],
        active_file_names: frozenset[str],
    ) -> PluginSourceBatchTextScan:
        """记录插件源码写回预演扫描过的文件。"""
        scanned_batches.append(tuple(sorted(files)))
        return real_runtime_batch_scan(
            files=files,
            active_file_names=active_file_names,
        )

    def forbidden_legacy_strict_scan(*args: object, **kwargs: object) -> PluginSourceBatchTextScan:
        _ = (args, kwargs)
        raise AssertionError("写回探针 fallback 不应调用翻译源 strict scan")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        successful_native_probe,
    )
    monkeypatch.setattr(
        "app.text_scope.write_probe.scan_plugin_source_files_text_strict",
        forbidden_legacy_strict_scan,
        raising=False,
    )
    monkeypatch.setattr(
        "app.text_scope.write_probe.scan_plugin_source_runtime_files_text_strict",
        counting_plugin_source_runtime_batch_scan,
        raising=False,
    )

    reasons = collect_write_back_probe_reasons(game_data=game_data, active_items=items)

    assert reasons == {}
    assert scanned_batches == [("HardcodedText.js", "HardcodedTextExtra.js")]


def _read_test_json_from_plugins_js(path: Path) -> JsonValue:
    """从测试 `plugins.js` 读取 `$plugins` 数组。"""
    text = path.read_text(encoding="utf-8")
    start = text.index("[")
    end = text.rindex("]") + 1
    return coerce_json_value(cast(object, json.loads(text[start:end])))
