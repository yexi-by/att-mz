"""Agent 工具包诊断、扫描和质量报告测试。"""

import json
from pathlib import Path
from typing import NoReturn, cast

import pytest

from app.agent_toolkit import AgentToolkitService
from app.application.handler import TranslationHandler
from app.config import SettingOverrides
from app.llm import LLMHandler
from app.persistence import GameRegistry
from app.plugin_text import build_plugin_hash
from app.rmmz.json_types import JsonArray, JsonObject, JsonValue, coerce_json_value, ensure_json_array, ensure_json_object
from app.rmmz.loader import load_game_data
from app.rmmz.schema import (
    EventCommandParameterFilter,
    EventCommandTextRuleRecord,
    NoteTagTextRuleRecord,
    PlaceholderRuleRecord,
    PluginTextRuleRecord,
    SourceResidualRuleRecord,
    TranslationErrorItem,
    TranslationItem,
)
from app.runtime_paths import APP_HOME_ENV_NAME
from app.terminology import TerminologyGlossary, TerminologyRegistry

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


def load_json_object(path: Path) -> dict[str, object]:
    """读取测试产物 JSON 对象，并在边界处收窄动态解析结果。"""
    raw_value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    json_object = ensure_json_object(coerce_json_value(raw_value), str(path))
    return {key: value for key, value in json_object.items()}


def load_json_array(path: Path) -> list[object]:
    """读取测试产物 JSON 数组，并在边界处收窄动态解析结果。"""
    raw_value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    json_array = ensure_json_array(coerce_json_value(raw_value), str(path))
    return [item for item in json_array]


def _contains_japanese_test_char(text: str) -> bool:
    """判断测试样本文本是否含有日文假名。"""
    return any("\u3040" <= char <= "\u30ff" for char in text)


@pytest.mark.asyncio
async def test_doctor_uses_fake_llm_check_without_real_request(tmp_path: Path) -> None:
    """doctor 可以注入模型检查函数，测试环境不触发真实 API。"""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    called_models: list[str] = []

    async def fake_llm_check(_llm_handler: LLMHandler, model: str) -> None:
        """记录模型名称，不发起网络请求。"""
        called_models.append(model)

    service = AgentToolkitService(
        game_registry=GameRegistry(db_dir),
        llm_check=fake_llm_check,
        setting_path=EXAMPLE_SETTING_PATH,
    )

    report = await service.doctor(game_title=None, check_llm=True)

    assert report.status in {"ok", "warning"}
    assert called_models
    assert report.summary["llm_model"]


@pytest.mark.asyncio
async def test_doctor_creates_missing_db_directory(tmp_path: Path) -> None:
    """doctor 会自愈创建缺失的固定数据库目录。"""
    db_dir = tmp_path / "missing-db"
    service = AgentToolkitService(
        game_registry=GameRegistry(db_dir),
        setting_path=EXAMPLE_SETTING_PATH,
    )

    report = await service.doctor(game_title=None, check_llm=False)

    error_codes = {error.code for error in report.errors}
    assert "db_dir" not in error_codes
    assert db_dir.exists()


@pytest.mark.asyncio
async def test_doctor_respects_reviewed_empty_rule_state_until_scope_changes(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """doctor 能区分规则未处理、已确认空结果和输入范围变化后的过期空结果。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    plugin_rules_path = tmp_path / "plugin-rules.json"
    event_rules_path = tmp_path / "event-command-rules.json"
    _ = plugin_rules_path.write_text("[]\n", encoding="utf-8")
    _ = event_rules_path.write_text("{}\n", encoding="utf-8")

    _ = await handler.import_plugin_rules(game_title="テストゲーム", input_path=plugin_rules_path)
    _ = await handler.import_event_command_rules(game_title="テストゲーム", input_path=event_rules_path)
    note_import_report = await service.import_note_tag_rules(game_title="テストゲーム", rules_text="{}")
    fresh_report = await service.doctor(game_title="テストゲーム", check_llm=False)

    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    parameters[2] = "追加参数"
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    stale_report = await service.doctor(game_title="テストゲーム", check_llm=False)

    assert note_import_report.status == "warning"
    fresh_warning_codes = {warning.code for warning in fresh_report.warnings}
    stale_warning_codes = {warning.code for warning in stale_report.warnings}
    assert "plugin_rules" not in fresh_warning_codes
    assert "event_command_rules" not in fresh_warning_codes
    assert "note_tag_rules" not in fresh_warning_codes
    assert fresh_report.summary["plugin_rules_reviewed_empty"] is True
    assert fresh_report.summary["event_command_rules_reviewed_empty"] is True
    assert fresh_report.summary["note_tag_rules_reviewed_empty"] is True
    assert stale_report.summary["event_command_rules_reviewed_empty"] is False
    assert stale_report.summary["event_command_rules_review_state_stale"] is True
    assert "event_command_rules_review_state_stale" in stale_warning_codes


@pytest.mark.asyncio
async def test_import_empty_plugin_rules_deletes_stale_plugin_translations(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件规则改为空结果时同步清理旧插件译文，避免后续写进游戏文件被旧路径阻断。"""
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(tmp_path / "app-home"))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    rules_path = tmp_path / "plugin-rules.json"
    empty_rules_path = tmp_path / "plugin-rules-empty.json"
    _ = rules_path.write_text(
        json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Message']"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _ = empty_rules_path.write_text("[]\n", encoding="utf-8")

    _ = await handler.import_plugin_rules(game_title="テストゲーム", input_path=rules_path)
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="plugins.js/0/Message",
                    item_type="short_text",
                    original_lines=["プラグイン台詞"],
                    translation_lines=["插件译文"],
                )
            ]
        )

    summary = await handler.import_plugin_rules(game_title="テストゲーム", input_path=empty_rules_path)
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()

    backup_path = summary.deleted_translation_backup_path
    assert summary.deleted_translation_items == 1
    assert backup_path is not None
    assert Path(backup_path).exists()
    backup_payload = load_json_object(Path(backup_path))
    backup_entry = ensure_json_object(coerce_json_value(backup_payload["plugins.js/0/Message"]), "backup_entry")
    assert backup_entry["translation_lines"] == ["插件译文"]
    assert translated_items == []

    _ = await handler.import_plugin_rules(game_title="テストゲーム", input_path=rules_path)
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    restore_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=Path(backup_path),
    )
    async with await registry.open_game("テストゲーム") as session:
        restored_items = await session.read_translated_items()

    assert restore_report.status == "ok"
    assert restored_items[0].location_path == "plugins.js/0/Message"
    assert restored_items[0].translation_lines == ["插件译文"]


@pytest.mark.asyncio
async def test_import_empty_event_command_rules_deletes_stale_event_translations(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令规则改为空结果时同步清理旧事件指令译文。"""
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(tmp_path / "app-home"))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    rules_path = tmp_path / "event-command-rules.json"
    empty_rules_path = tmp_path / "event-command-rules-empty.json"
    _ = rules_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": ["$['parameters'][3]['message']"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _ = empty_rules_path.write_text("{}\n", encoding="utf-8")

    _ = await handler.import_event_command_rules(game_title="テストゲーム", input_path=rules_path)
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/4/parameters/3/message",
                    item_type="short_text",
                    original_lines=["プラグイン台詞"],
                    translation_lines=["事件指令译文"],
                )
            ]
        )

    summary = await handler.import_event_command_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
    )
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()

    backup_path = summary.deleted_translation_backup_path
    assert summary.deleted_translation_items == 1
    assert backup_path is not None
    assert Path(backup_path).exists()
    backup_payload = load_json_object(Path(backup_path))
    backup_entry = ensure_json_object(
        coerce_json_value(backup_payload["CommonEvents.json/1/4/parameters/3/message"]),
        "backup_entry",
    )
    assert backup_entry["translation_lines"] == ["事件指令译文"]
    assert translated_items == []


@pytest.mark.asyncio
async def test_text_scope_and_audit_coverage_use_unified_contract(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """统一文本清单和覆盖审计暴露同一批可处理文本。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    scope_report = await service.text_scope(game_title="テストゲーム")
    audit_report = await service.audit_coverage(game_title="テストゲーム")

    entries = ensure_json_array(scope_report.details["entries"], "entries")
    first_entry = ensure_json_object(entries[0], "entries[0]")
    assert scope_report.status == "ok"
    assert scope_report.summary["entry_count"] == len(entries)
    assert first_entry.keys() >= {
        "location_path",
        "source_type",
        "rule_source",
        "original_lines",
        "enters_translation",
        "can_save_translation",
        "can_write_back",
        "cannot_process_reason",
    }
    assert audit_report.status == "error"
    assert audit_report.summary["extractable_count"] == scope_report.summary["extractable_count"]
    assert audit_report.summary["pending_count"] == scope_report.summary["extractable_count"]


@pytest.mark.asyncio
async def test_text_scope_and_audit_coverage_use_real_write_probe(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """统一文本清单的可写状态来自真实写入协议探针。"""

    def fake_collect_native_write_protocol_details(
        *,
        game_data: JsonObject,
        plugins_js: list[JsonValue],
        items: list[TranslationItem],
    ) -> list[JsonValue]:
        """把第一条文本标记为不可写，模拟 Rust 写入协议失败。"""
        _ = (game_data, plugins_js)
        return [{"location_path": items[0].location_path, "reason": "探针失败"}]

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        fake_collect_native_write_protocol_details,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    scope_report = await service.text_scope(game_title="テストゲーム")
    audit_report = await service.audit_coverage(game_title="テストゲーム")
    unwritable_items = ensure_json_array(scope_report.details["unwritable_items"], "unwritable_items")
    first_unwritable = ensure_json_object(unwritable_items[0], "unwritable_items[0]")

    assert scope_report.summary["unwritable_count"] == 1
    assert first_unwritable["can_write_back"] is False
    assert first_unwritable["cannot_process_reason"] == "探针失败"
    assert audit_report.status == "error"
    assert {error.code for error in audit_report.errors} >= {"coverage_unwritable"}
    extractable_count = scope_report.summary["extractable_count"]
    assert isinstance(extractable_count, int)
    assert audit_report.summary["writable_count"] == extractable_count - 1


@pytest.mark.asyncio
async def test_text_scope_reports_global_write_probe_failure(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写入协议探针整体不可用时返回全局错误，不伪装成每条文本不可写。"""

    def broken_collect_native_write_protocol_details(
        *,
        game_data: JsonObject,
        plugins_js: list[JsonValue],
        items: list[TranslationItem],
    ) -> list[JsonValue]:
        """模拟原生探针基础设施故障。"""
        _ = (game_data, plugins_js, items)
        raise RuntimeError("native probe unavailable")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        broken_collect_native_write_protocol_details,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    scope_report = await service.text_scope(game_title="テストゲーム")
    audit_report = await service.audit_coverage(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert scope_report.status == "error"
    assert audit_report.status == "error"
    assert quality_report.status == "error"
    assert {error.code for error in scope_report.errors} == {"write_probe_failed"}
    assert {error.code for error in audit_report.errors} >= {"write_probe_failed"}
    assert {error.code for error in quality_report.errors} >= {"write_probe_failed"}
    assert scope_report.summary["write_back_probe_failed"] is True
    assert scope_report.summary["unwritable_count"] == 0


@pytest.mark.asyncio
async def test_text_scope_reports_partial_write_probe_failure_per_item(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写入协议探针部分失败时必须标记具体条目，不把坏路径当成可写。"""
    failed_single_path = ""

    def flaky_collect_native_write_protocol_details(
        *,
        game_data: JsonObject,
        plugins_js: list[JsonValue],
        items: list[TranslationItem],
    ) -> list[JsonValue]:
        """模拟批量探针失败、逐条探针仅一个条目失败。"""
        nonlocal failed_single_path
        _ = (game_data, plugins_js)
        if len(items) > 1:
            raise RuntimeError("batch probe unavailable")
        item = items[0]
        if not failed_single_path:
            failed_single_path = item.location_path
            raise RuntimeError("single path probe unavailable")
        return []

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        flaky_collect_native_write_protocol_details,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    scope_report = await service.text_scope(game_title="テストゲーム")

    assert scope_report.status == "error"
    assert failed_single_path
    assert scope_report.summary["write_back_probe_failed"] is False
    assert scope_report.summary["unwritable_count"] == 1
    unwritable_items = ensure_json_array(scope_report.details["unwritable_items"], "unwritable_items")
    first_unwritable = ensure_json_object(unwritable_items[0], "unwritable_items[0]")
    assert first_unwritable["location_path"] == failed_single_path
    reason = first_unwritable["cannot_process_reason"]
    assert isinstance(reason, str)
    assert "写入协议探针失败" in reason


@pytest.mark.asyncio
async def test_quality_report_stops_on_coverage_error_before_native_checks(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """覆盖审计不通过时，质量报告不能继续执行后续原生质检。"""

    def fake_scope_write_protocol(
        *,
        game_data: JsonObject,
        plugins_js: list[JsonValue],
        items: list[TranslationItem],
    ) -> list[JsonValue]:
        """把第一条文本标记为不可写，制造覆盖审计错误。"""
        _ = (game_data, plugins_js)
        return [{"location_path": items[0].location_path, "reason": "探针失败"}]

    def forbidden_quality_check(*args: object, **kwargs: object) -> NoReturn:
        """覆盖错误后不应再进入译文本体质检。"""
        _ = (args, kwargs)
        raise AssertionError("覆盖错误后不应继续执行译文本体质检")

    def forbidden_write_protocol(*args: object, **kwargs: object) -> NoReturn:
        """覆盖错误后不应再进入写入协议质检。"""
        _ = (args, kwargs)
        raise AssertionError("覆盖错误后不应继续执行写入协议质检")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        fake_scope_write_protocol,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.service.collect_native_quality_details",
        forbidden_quality_check,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.service.collect_native_write_protocol_details",
        forbidden_write_protocol,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.quality_report(game_title="テストゲーム")

    assert report.status == "error"
    assert "coverage_unwritable" in {error.code for error in report.errors}
    assert report.summary["source_residual_count"] == 0
    assert report.summary["write_back_protocol_count"] == 0


@pytest.mark.asyncio
async def test_export_quality_fix_template_stops_on_text_scope_blocker(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """质量修复表遇到文本范围阻断错误时不能继续生成半可信结果。"""

    def fake_scope_write_protocol(
        *,
        game_data: JsonObject,
        plugins_js: list[JsonValue],
        items: list[TranslationItem],
    ) -> list[JsonValue]:
        """把第一条文本标记为不可写，制造文本范围阻断错误。"""
        _ = (game_data, plugins_js)
        return [{"location_path": items[0].location_path, "reason": "探针失败"}]

    def forbidden_quality_check(*args: object, **kwargs: object) -> NoReturn:
        """文本范围阻断后不应再进入译文本体质检。"""
        _ = (args, kwargs)
        raise AssertionError("文本范围阻断后不应继续执行译文本体质检")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        fake_scope_write_protocol,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.service.collect_native_quality_details",
        forbidden_quality_check,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "quality-fix.json"

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=output_path,
    )

    assert report.status == "error"
    assert "coverage_unwritable" in {error.code for error in report.errors}
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_read_only_placeholder_scan_does_not_run_write_probe(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只读占位符候选扫描不能暗中执行写入探针。"""

    def forbidden_write_probe(*args: object, **kwargs: object) -> NoReturn:
        """只读扫描不应触碰写入协议探针。"""
        _ = (args, kwargs)
        raise AssertionError("只读扫描不应执行写入探针")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        forbidden_write_probe,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.scan_placeholder_candidates(
        game_title="テストゲーム",
        custom_placeholder_rules_text=None,
    )

    assert report.status in {"ok", "warning"}
    assert "candidate_count" in report.summary


@pytest.mark.asyncio
async def test_validate_placeholder_rules_blocks_translatable_text_loss() -> None:
    """自定义占位符规则不能把含源语言正文的样本文本整体吞掉。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    unsafe_report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps({r"こんにちは": "[CUSTOM_SWALLOW_{index}]"}, ensure_ascii=False),
        sample_texts=["こんにちは"],
    )
    safe_report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps({r"^◆<[^>]+>ｔ": "[CUSTOM_VOICE_{index}]"}, ensure_ascii=False),
        sample_texts=["◆<アリス>ｔこんにちは"],
    )

    unsafe_error_codes = {error.code for error in unsafe_report.errors}
    safe_error_codes = {error.code for error in safe_report.errors}
    assert "placeholder_rule_loses_translatable_text" in unsafe_error_codes
    assert "placeholder_rule_loses_translatable_text" not in safe_error_codes


@pytest.mark.asyncio
async def test_feedback_verification_and_plugin_source_scan_are_structural_only(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """反馈反查和插件源码扫描只报告结构性命中，不自动判定玩家可见语义。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), str(common_events_path))
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    command_list = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    parameters: JsonArray = ["一行\n二行"]
    command: JsonObject = {"code": 401, "parameters": parameters}
    command_list.insert(2, command)
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir()
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "\n".join(
            [
                "Window_Base.prototype.drawText('プラグイン直書き', 0, 0, 320);",
                "Window_Base.prototype.drawText('img/system/IconSet.png', 0, 0, 320);",
            ]
        ),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    feedback_path = tmp_path / "feedback-texts.json"
    candidates_path = tmp_path / "plugin-source-candidates.json"
    _ = feedback_path.write_text(
        json.dumps(["こんにちは", "プラグイン直書き", "一行\n二行"], ensure_ascii=False),
        encoding="utf-8",
    )

    verify_report = await service.verify_feedback_text(game_title="テストゲーム", input_path=feedback_path)
    scan_report = await service.scan_plugin_source_text(game_title="テストゲーム", output_path=candidates_path)
    candidates = load_json_array(candidates_path)
    occurrence_count = verify_report.summary["occurrence_count"]

    assert verify_report.status == "error"
    assert isinstance(occurrence_count, int)
    assert occurrence_count >= 1
    occurrences = ensure_json_array(verify_report.details["occurrences"], "occurrences")
    gap_types: set[str] = set()
    for occurrence in occurrences:
        occurrence_object = ensure_json_object(coerce_json_value(occurrence), "occurrence")
        gap_type = occurrence_object.get("gap_type")
        if isinstance(gap_type, str):
            gap_types.add(gap_type)
    assert "translation_gap" in gap_types
    assert "plugin_source_hardcoded" in gap_types
    assert any(
        ensure_json_object(coerce_json_value(occurrence), "occurrence").get("text") == "一行\n二行"
        for occurrence in occurrences
    )
    assert scan_report.status == "ok"
    assert any(
        ensure_json_object(coerce_json_value(candidate), "candidate").get("text") == "プラグイン直書き"
        for candidate in candidates
    )
    resource_candidate = next(
        ensure_json_object(coerce_json_value(candidate), "candidate")
        for candidate in candidates
        if ensure_json_object(coerce_json_value(candidate), "candidate").get("text") == "img/system/IconSet.png"
    )
    assert resource_candidate["structural_flags"] == ["resource_path_like", "identifier_or_path_like"]


@pytest.mark.asyncio
async def test_feedback_verification_reads_active_files_not_origin_backups(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """反馈反查必须检查当前激活文件，不能把原件留档误报成激活文件残留。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    origin_data_dir = minimal_game_dir / "data_origin"
    origin_data_dir.mkdir()
    origin_items = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    active_items = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    origin_item = ensure_json_object(ensure_json_array(origin_items, "origin Items.json")[1], "origin Items.json[1]")
    active_item = ensure_json_object(ensure_json_array(active_items, "active Items.json")[1], "active Items.json[1]")
    origin_item["description"] = "With this rope..."
    active_item["description"] = "有了这根绳子，说不定能到达世界的中心。"
    _ = (origin_data_dir / "Items.json").write_text(json.dumps(origin_items, ensure_ascii=False, indent=2), encoding="utf-8")
    _ = items_path.write_text(json.dumps(active_items, ensure_ascii=False, indent=2), encoding="utf-8")

    active_plugins = [
        {
            "name": "OriginOnlyPlugin",
            "status": True,
            "description": "已修复",
            "parameters": {"message": "是否读取此存档文件？"},
        }
    ]
    origin_plugins = [
        {
            "name": "OriginOnlyPlugin",
            "status": True,
            "description": "original",
            "parameters": {"message": "Whether to load this save file?"},
        }
    ]
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_origin_path = minimal_game_dir / "js" / "plugins_origin.js"
    _ = plugins_path.write_text(f"var $plugins = {json.dumps(active_plugins, ensure_ascii=False, indent=2)};\n", encoding="utf-8")
    _ = plugins_origin_path.write_text(f"var $plugins = {json.dumps(origin_plugins, ensure_ascii=False, indent=2)};\n", encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    feedback_path = tmp_path / "feedback-texts.json"
    _ = feedback_path.write_text(
        json.dumps(["With this rope...", "Whether to load this save file?"], ensure_ascii=False),
        encoding="utf-8",
    )

    report = await service.verify_feedback_text(game_title="テストゲーム", input_path=feedback_path)

    assert report.status == "ok"
    assert report.summary["occurrence_count"] == 0
    assert report.details["occurrences"] == []


@pytest.mark.asyncio
async def test_import_placeholder_rules_runs_validation_before_save(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """占位符规则导入不能绕过可翻译内容损失校验。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({r"こんにちは": "[CUSTOM_SWALLOW_{index}]"}, ensure_ascii=False),
    )

    assert report.status == "error"
    assert "placeholder_rule_loses_translatable_text" in {error.code for error in report.errors}
    async with await registry.open_game("テストゲーム") as session:
        records = await session.read_placeholder_rules()
    assert records == []


@pytest.mark.asyncio
async def test_english_profile_exports_visible_pending_text_without_protocol_noise(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """英文档案能提取玩家可见英文，并跳过资源路径、公式和布尔值。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-english.json"
    workspace_path = tmp_path / "workspace"

    async with await registry.open_game("English Fixture Game") as session:
        game_data = await load_game_data(session.game_path)
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="VisiblePlugin",
                    plugin_hash=build_plugin_hash(game_data.plugins_js[0]),
                    path_templates=[
                        "$['parameters']['Message']",
                        "$['parameters']['Title']",
                        "$['parameters']['Image']",
                        "$['parameters']['Formula']",
                        "$['parameters']['Enabled']",
                    ],
                )
            ]
        )

    workspace_report = await service.prepare_agent_workspace(
        game_title="English Fixture Game",
        output_dir=workspace_path,
        command_codes=None,
    )
    export_report = await service.export_pending_translations(
        game_title="English Fixture Game",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    exported_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        exported_lines.extend(
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        )

    assert workspace_report.status in {"ok", "warning"}
    assert workspace_report.summary["source_language"] == "en"
    assert export_report.status == "ok"
    assert "Are you really going in there?" in exported_lines
    assert "Open the door" in exported_lines
    assert "Welcome to the old gate." in exported_lines
    assert "Gate Menu" in exported_lines
    assert "img/pictures/Gate.png" not in exported_lines
    assert "a.hpRate() >= 0.5" not in exported_lines
    assert "true" not in exported_lines


@pytest.mark.asyncio
async def test_scan_placeholder_candidates_marks_custom_rule_coverage(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """扫描命令能区分内置控制符、未覆盖自定义控制符和 CLI 覆盖规则。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    uncovered_report = await service.scan_placeholder_candidates(
        game_title="テストゲーム",
        custom_placeholder_rules_text="{}",
    )
    covered_report = await service.scan_placeholder_candidates(
        game_title="テストゲーム",
        custom_placeholder_rules_text='{"\\\\\\\\F\\\\[[^\\\\]]+\\\\]":"[CUSTOM_FACE_PORTRAIT_{index}]"}',
    )

    assert uncovered_report.summary["uncovered_count"] != 0
    assert covered_report.summary["uncovered_count"] == 0
    raw_json = covered_report.to_json_text()
    assert r"\F[GuideA]" in raw_json
    assert "テスト一行目です" not in raw_json


@pytest.mark.asyncio
async def test_build_placeholder_rules_groups_similar_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """规则草稿会把同类自定义控制符合并成少量通用正则。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=output_path)

    assert report.status == "ok"
    rules = load_json_object(output_path)
    uncovered_before = report.summary["uncovered_count_before_draft"]
    assert rules == {r"(?i)\\F\d*\[[^\]\r\n]+\]": "[CUSTOM_FACE_PORTRAIT_{index}]"}
    assert report.summary["draft_rule_count"] == 1
    assert isinstance(uncovered_before, int)
    assert uncovered_before > 0
    assert report.summary["uncovered_count_after_draft_preview"] == 0


@pytest.mark.asyncio
async def test_build_placeholder_rules_keeps_bare_uppercase_marker_case_sensitive(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """裸大写自定义标记草稿不能忽略大小写误匹配字面量换行。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_value = coerce_json_value(cast(object, json.loads(common_events_path.read_text(encoding="utf-8"))))
    common_events = ensure_json_array(raw_value, "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    text_command = ensure_json_object(commands[1], "CommonEvents.json[1].list[1]")
    parameters = ensure_json_array(text_command["parameters"], "CommonEvents.json[1].list[1].parameters")
    parameters[0] = r"\N<案内人>こんにちは"
    _ = common_events_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=output_path)

    assert report.status == "ok"
    rules = load_json_object(output_path)
    assert rules[r"\\N\d*(?![A-Za-z\[])"] == "[CUSTOM_PLUGIN_N_MARKER_{index}]"
    assert r"(?i)\\N\d*(?![A-Za-z\[])" not in rules


@pytest.mark.asyncio
async def test_build_placeholder_rules_requires_manual_boundary_for_joined_control_text(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """英文正文紧贴无参数控制符时，草稿不自动猜测短前缀。"""
    common_events_path = minimal_english_game_dir / "data" / "CommonEvents.json"
    raw_value = coerce_json_value(cast(object, json.loads(common_events_path.read_text(encoding="utf-8"))))
    common_events = ensure_json_array(raw_value, "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands[1:1] = [
        {"code": 401, "parameters": [r"\ShakeStop this!!!"]},
        {"code": 401, "parameters": [r"\ShakeNo, NO!!!"]},
        {"code": 401, "parameters": [r"\ShakeAhhh..."]},
        {"code": 401, "parameters": [r"\FXStop this!!!"]},
        {"code": 401, "parameters": [r"\ScreenShake"]},
        {"code": 401, "parameters": [r"\ScreenFlash"]},
    ]
    _ = common_events_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="English Fixture Game", output_path=output_path)
    rules = load_json_object(output_path)
    warning_codes = {warning.code for warning in report.warnings}
    manual_coverage_report = await service.scan_placeholder_candidates(
        game_title="English Fixture Game",
        custom_placeholder_rules_text=json.dumps(
            {r"\\Shake": "[CUSTOM_PLUGIN_SHAKE_MARKER_{index}]"},
            ensure_ascii=False,
        ),
    )
    manual_coverage_json = manual_coverage_report.to_json_text()

    assert report.status == "warning"
    assert rules == {}
    assert report.summary["manual_boundary_candidate_count"] == 6
    assert report.summary["uncovered_count_after_draft_preview"] == report.summary["uncovered_count_before_draft"]
    assert "placeholder_boundary_needs_review" in warning_codes
    assert r"\Screen" not in json.dumps(rules, ensure_ascii=False)
    assert r"\FXStop" not in json.dumps(rules, ensure_ascii=False)
    assert manual_coverage_report.summary["uncovered_count"] == 3
    assert r"\ShakeStop" not in manual_coverage_json
    assert r"\Shake" in manual_coverage_json


@pytest.mark.asyncio
async def test_placeholder_rule_draft_uses_active_translation_sources(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """占位符草稿只基于当前会进入翻译正文的完整文本集合。"""
    game_data = await load_game_data(minimal_game_dir)
    plugin_parameters = ensure_json_object(game_data.plugins_js[0]["parameters"], "plugins[0].parameters")
    plugin_parameters["Message"] = r"\PX[PluginFace]プラグイン本文"
    plugins_text = f"var $plugins = {json.dumps(game_data.plugins_js, ensure_ascii=False, indent=2)};\n"
    _ = (minimal_game_dir / "js" / "plugins.js").write_text(plugins_text, encoding="utf-8")

    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    payload = ensure_json_object(parameters[3], "CommonEvents[1].list[4].parameters[3]")
    payload["message"] = r"\EV[CommandFace]プラグイン台詞"
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")

    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = r"<拡張説明:\NT[NoteFace]薬草の詳細説明>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    before_rules_path = tmp_path / "before-placeholder-rules.json"
    after_rules_path = tmp_path / "after-placeholder-rules.json"

    _ = await service.build_placeholder_rules(game_title="テストゲーム", output_path=before_rules_path)
    before_rules = load_json_object(before_rules_path)

    fresh_game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(fresh_game_data.plugins_js[0]),
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[
                        EventCommandParameterFilter(index=0, value="TestPlugin"),
                        EventCommandParameterFilter(index=1, value="Show"),
                    ],
                    path_templates=["$['parameters'][3]['message']"],
                )
            ]
        )
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
        )

    report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=after_rules_path)
    after_rules = load_json_object(after_rules_path)
    draft_rule_count = report.summary["draft_rule_count"]

    assert isinstance(draft_rule_count, int)
    assert draft_rule_count >= 4
    assert not any(r"\\PX" in pattern for pattern in before_rules)
    assert not any(r"\\EV" in pattern for pattern in before_rules)
    assert not any(r"\\NT" in pattern for pattern in before_rules)
    assert any(r"\\PX" in pattern for pattern in after_rules)
    assert any(r"\\EV" in pattern for pattern in after_rules)
    assert any(r"\\NT" in pattern for pattern in after_rules)


@pytest.mark.asyncio
async def test_prepare_agent_workspace_includes_placeholder_rule_draft(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 工作区会携带占位符和 Note 标签规则草稿，避免重复手写解析脚本。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )

    assert report.status == "ok"
    rules_path = workspace / "placeholder-rules.json"
    note_candidates_path = workspace / "note-tag-candidates.json"
    note_rules_path = workspace / "note-tag-rules.json"
    plugin_json_string_candidates_path = workspace / "plugin-json-string-leaf-candidates.json"
    field_terms_path = workspace / "terminology" / "field-terms.json"
    glossary_path = workspace / "terminology" / "glossary.json"
    speaker_source_path = workspace / "terminology" / "subtasks" / "sources" / "speaker_and_actor_terms.json"
    speaker_candidate_path = workspace / "terminology" / "subtasks" / "candidates" / "speaker_and_actor_terms.json"
    item_source_path = workspace / "terminology" / "subtasks" / "sources" / "item_terms.json"
    item_candidate_path = workspace / "terminology" / "subtasks" / "candidates" / "item_terms.json"
    manifest_path = workspace / "manifest.json"
    assert rules_path.exists()
    assert note_candidates_path.exists()
    assert note_rules_path.exists()
    assert plugin_json_string_candidates_path.exists()
    assert field_terms_path.exists()
    assert glossary_path.exists()
    assert speaker_source_path.exists()
    assert speaker_candidate_path.exists()
    assert item_source_path.exists()
    assert item_candidate_path.exists()
    assert manifest_path.exists()
    rules = load_json_object(rules_path)
    plugin_json_string_candidates = load_json_array(plugin_json_string_candidates_path)
    note_rules = load_json_object(note_rules_path)
    glossary = load_json_object(glossary_path)
    speaker_source = load_json_object(speaker_source_path)
    speaker_candidate = load_json_object(speaker_candidate_path)
    item_source = load_json_object(item_source_path)
    item_candidate = load_json_object(item_candidate_path)
    manifest = load_json_object(manifest_path)
    layout = ensure_json_object(coerce_json_value(manifest["layout"]), "manifest.layout")
    speaker_names = ensure_json_object(coerce_json_value(speaker_source["speaker_names"]), "speaker_names")
    item_names = ensure_json_object(coerce_json_value(item_source["item_names"]), "item_names")
    workflow = ensure_json_object(coerce_json_value(manifest["workflow"]), "manifest.workflow")
    subagent_rounds = ensure_json_array(
        coerce_json_value(cast(object, workflow["subagent_rounds"])),
        "manifest.workflow.subagent_rounds",
    )
    first_round = ensure_json_object(subagent_rounds[0], "manifest.workflow.subagent_rounds[0]")
    second_round = ensure_json_object(subagent_rounds[1], "manifest.workflow.subagent_rounds[1]")
    plugin_json_string_leaf_candidate_count = report.summary["plugin_json_string_leaf_candidate_count"]
    assert rules == {r"(?i)\\F\d*\[[^\]\r\n]+\]": "[CUSTOM_FACE_PORTRAIT_{index}]"}
    assert isinstance(plugin_json_string_leaf_candidate_count, int)
    assert plugin_json_string_leaf_candidate_count >= 2
    assert any(
        "$['parameters']['Nested']['text']"
        in ensure_json_array(
            ensure_json_object(coerce_json_value(raw_candidate), "plugin-json-string-leaf-candidates[]")[
                "string_leaf_path_candidates"
            ],
            "string_leaf_path_candidates",
        )
        for raw_candidate in plugin_json_string_candidates
    )
    assert note_rules == {}
    assert glossary == {"terms": {}}
    assert speaker_source == speaker_candidate
    assert item_source == item_candidate
    assert "村人" in speaker_names
    assert "回復薬" in item_names
    assert layout["engine_kind"] == "mz"
    assert report.summary["event_command_codes"] == [357]
    assert report.summary["placeholder_rule_draft_count"] == 1
    assert report.summary["terminology_subtask_count"] == 5
    assert first_round["name"] == "terminology_candidates"
    assert first_round["owner"] == "主代理"
    assert second_round["name"] == "external_text_rules"
    assert "placeholder_phase" in workflow
    assert "plugin-json-string-leaf-candidates.json" in json.dumps(report.details, ensure_ascii=False)
    assert "note-tag-rules.json" in json.dumps(report.details, ensure_ascii=False)


@pytest.mark.asyncio
async def test_validate_plugin_rules_reports_json_string_leaf_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件规则误指向 JSON 字符串容器时，校验报告提示可写内部字符串叶子。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    rejected_report = await service.validate_plugin_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Nested']"],
                }
            ],
            ensure_ascii=False,
        ),
    )
    accepted_report = await service.validate_plugin_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Nested']['text']"],
                }
            ],
            ensure_ascii=False,
        ),
    )

    assert rejected_report.status == "error"
    assert "解析后的内部字符串叶子" in rejected_report.errors[0].message
    assert "$['parameters']['Nested']['text']" in rejected_report.errors[0].message
    assert accepted_report.status == "ok"


@pytest.mark.asyncio
async def test_prepare_agent_workspace_uses_mv_event_command_default(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 工作区摘要和事件指令样本按 356 插件命令生成。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "mv-workspace"

    report = await service.prepare_agent_workspace(
        game_title="MVテストゲーム",
        output_dir=workspace,
        command_codes=None,
    )

    event_commands = load_json_object(workspace / "event-commands.json")
    manifest = load_json_object(workspace / "manifest.json")
    layout = ensure_json_object(coerce_json_value(manifest["layout"]), "manifest.layout")
    commands = ensure_json_array(coerce_json_value(event_commands["356"]), "event-commands.356")
    assert report.status == "ok"
    assert report.summary["engine_kind"] == "mv"
    assert report.summary["event_command_codes"] == [356]
    assert layout["engine_kind"] == "mv"
    assert "www" in str(layout["data_dir"])
    assert len(commands) == 1


@pytest.mark.asyncio
async def test_prepare_agent_workspace_prefills_imported_database_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """二次翻译工作区会回填当前数据库中已导入的规则和术语表。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    first_item = ensure_json_object(items[1], "Items.json[1]")
    first_item["note"] = "<拡張説明:薬草の詳細説明>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    seed_workspace = tmp_path / "seed-workspace"
    workspace = tmp_path / "workspace"

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=seed_workspace,
        command_codes=None,
    )
    exported_registry = TerminologyRegistry.model_validate(
        load_json_object(seed_workspace / "terminology" / "field-terms.json")
    )
    filled_registry = TerminologyRegistry.from_category_map(
        {
            category: {
                source_text: f"{source_text}译"
                for source_text in entries
            }
            for category, entries in exported_registry.as_category_map().items()
        }
    )
    game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_registry(filled_registry)
        await session.replace_terminology_glossary(
            TerminologyGlossary(terms={"火の術": "火术"})
        )
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(game_data.plugins_js[0]),
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[EventCommandParameterFilter(index=0, value="TestPlugin")],
                    path_templates=["$['parameters'][3]['message']"],
                )
            ]
        )
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
        )
        await session.replace_placeholder_rules(
            [
                PlaceholderRuleRecord(
                    pattern_text=r"(?i)\\F\d*\[[^\]\r\n]+\]",
                    placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
                )
            ]
        )

    report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    validation_report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    prepared_registry = TerminologyRegistry.model_validate(
        load_json_object(workspace / "terminology" / "field-terms.json")
    )
    prepared_glossary = TerminologyGlossary.model_validate(
        load_json_object(workspace / "terminology" / "glossary.json")
    )
    plugin_rules = load_json_array(workspace / "plugin-rules.json")
    event_rules = load_json_object(workspace / "event-command-rules.json")
    note_rules = load_json_object(workspace / "note-tag-rules.json")
    placeholder_rules = load_json_object(workspace / "placeholder-rules.json")
    warning_codes = {warning.code for warning in validation_report.warnings}
    assert report.status == "ok"
    assert report.summary["plugin_rule_count"] == 1
    assert report.summary["event_command_rule_count"] == 1
    assert report.summary["note_tag_rule_count"] == 1
    assert report.summary["placeholder_rule_count"] == 1
    assert report.summary["glossary_term_count"] == 1
    assert prepared_registry == filled_registry
    assert prepared_glossary == TerminologyGlossary(terms={"火の術": "火术"})
    assert plugin_rules == [
        {
            "plugin_index": 0,
            "plugin_name": "TestPlugin",
            "paths": ["$['parameters']['Message']"],
        }
    ]
    assert event_rules == {
        "357": [
            {
                "match": {"0": "TestPlugin"},
                "paths": ["$['parameters'][3]['message']"],
            }
        ]
    }
    assert note_rules == {"Items.json": ["拡張説明"]}
    assert placeholder_rules == {r"(?i)\\F\d*\[[^\]\r\n]+\]": "[CUSTOM_FACE_PORTRAIT_{index}]"}
    assert validation_report.status == "ok"
    assert "plugin_rules_missing" not in warning_codes
    assert "event_command_rules_missing" not in warning_codes
    assert "terminology_empty_translation" not in warning_codes


@pytest.mark.asyncio
async def test_validate_agent_workspace_blocks_missing_note_tag_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签规则是第二轮三类规则产物之一，缺失时工作区校验阻断。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    (workspace / "note-tag-rules.json").unlink()
    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert report.status == "error"
    assert "note_tag_rules_missing" in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_validate_agent_workspace_reports_invalid_terminology_file(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """工作区验收会把坏术语表报告成结构化错误。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    _ = (workspace / "terminology" / "field-terms.json").write_text("{}\n", encoding="utf-8")

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert report.status == "error"
    assert "terminology_validate_failed" in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_validate_agent_workspace_reports_invalid_glossary_file(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """工作区验收会把坏正文术语表报告成结构化错误。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    _ = (workspace / "terminology" / "glossary.json").write_text(
        json.dumps({"terms": {"小明": "小明"}, "note": "不允许"}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert report.status == "error"
    assert "glossary_validate_failed" in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_validate_agent_workspace_blocks_uncovered_placeholder_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """工作区验收会阻断未覆盖当前正文控制符的占位符规则。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    _ = (workspace / "placeholder-rules.json").write_text("{}\n", encoding="utf-8")

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert report.status == "error"
    assert "placeholder_coverage_uncovered" in {error.code for error in report.errors}
    placeholder_coverage = ensure_json_object(report.details["placeholder_coverage"], "placeholder_coverage")
    summary = ensure_json_object(placeholder_coverage["summary"], "placeholder_coverage.summary")
    assert summary["uncovered_count"] != 0


@pytest.mark.asyncio
async def test_validate_agent_workspace_reports_invalid_placeholder_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """工作区验收会把坏占位符规则报告成结构化错误。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    _ = (workspace / "placeholder-rules.json").write_text("{\n", encoding="utf-8")

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    error_codes = {error.code for error in report.errors}
    assert report.status == "error"
    assert "placeholder_rules_invalid" in error_codes
    assert "placeholder_coverage_scan_failed" in error_codes


@pytest.mark.asyncio
async def test_note_tag_rule_validation_import_and_pending_export(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签规则校验后会让目标标签值进入 pending，机器协议标签会被拒绝。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:一行目\n二行目>\n<upgrade:1,2,3>\n<ExtendDesc:別説明>"
    items.append({"id": 2, "name": "空タグ項目", "note": "<拡張説明:>", "description": ""})
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    candidates_path = tmp_path / "note-tag-candidates.json"
    pending_path = tmp_path / "pending-translations.json"
    rules_text = json.dumps(
        {"Items.json": ["拡張説明", "ExtendDesc"]},
        ensure_ascii=False,
    )
    machine_rules_text = json.dumps({"Items.json": ["upgrade"]}, ensure_ascii=False)

    candidate_report = await service.export_note_tag_candidates(
        game_title="テストゲーム",
        output_path=candidates_path,
    )
    validate_report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    rejected_report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=machine_rules_text,
    )
    import_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )

    payload = load_json_object(pending_path)
    assert candidate_report.status == "ok"
    assert candidates_path.exists()
    assert validate_report.status == "ok"
    assert validate_report.summary["hit_count"] == 2
    assert rejected_report.status == "error"
    assert "机器协议" in rejected_report.errors[0].message
    assert import_report.status == "ok"
    assert export_report.status == "ok"
    assert "Items.json/1/note/拡張説明" in payload
    assert "Items.json/1/note/ExtendDesc" in payload
    assert "Items.json/2/note/拡張説明" not in payload


@pytest.mark.asyncio
async def test_manual_pending_translation_export_and_import(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 可以导出少量待翻译条目，人工补齐后再由工具校验入库。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=10,
    )

    assert export_report.status == "ok"
    payload = load_json_object(pending_path)
    target_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        if original_lines == ["こんにちは"]:
            target_path = location_path
            entry["translation_lines"] = ["　你好　"]
            payload[location_path] = entry
            break
    assert target_path
    _ = pending_path.write_text(json.dumps({target_path: payload[target_path]}, ensure_ascii=False, indent=2), encoding="utf-8")
    async with await registry.open_game("テストゲーム") as session:
        run_record = await session.start_translation_run(
            total_extracted=10,
            pending_count=10,
            deduplicated_count=10,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=["こんにちは"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["人工补译前的历史错误"],
                    model_response='{"bad": true}',
                )
            ],
        )

    import_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )
    status_report = await service.translation_status(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert import_report.status == "ok"
    assert status_report.summary["pending_count"] == quality_report.summary["pending_count"]
    assert status_report.summary["run_pending_count"] == 10
    assert status_report.summary["quality_error_count"] == 0
    assert status_report.summary["run_quality_error_count"] == 0
    assert quality_report.summary["quality_error_count"] == 0
    assert quality_report.summary["run_quality_error_count"] == 0
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        quality_errors = await session.read_translation_quality_errors(run_record.run_id)
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines == ["你好"]
    assert quality_errors == []


@pytest.mark.asyncio
async def test_manual_translation_rejects_changed_unprotected_control_sequence(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """人工补译不得改写未被占位符规则覆盖的疑似控制符。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    commands.insert(-1, {"code": 101, "parameters": [0, 0, 0, 2, "アリス"]})
    commands.insert(-1, {"code": 401, "parameters": [r"\F3[66」「ふーん……？」"]})
    _ = common_events_path.write_text(
        json.dumps(common_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    target_entry: JsonObject = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        if original_lines == [r"\F3[66」「ふーん……？」"]:
            target_path = location_path
            entry["translation_lines"] = [r"\F3[60」「唔——嗯……？」"]
            target_entry = {key: value for key, value in entry.items()}
            break
    assert export_report.status == "ok"
    assert target_path
    _ = pending_path.write_text(
        json.dumps({target_path: target_entry}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rejected_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert rejected_report.status == "error"
    assert rejected_report.errors
    assert "疑似控制符不一致" in rejected_report.errors[0].message
    assert r"\F3[66」" in rejected_report.errors[0].message
    assert r"\F3[60」" in rejected_report.errors[0].message


@pytest.mark.asyncio
async def test_manual_translation_uses_source_residual_exception_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """确需保留的源文片段必须先导入显式例外规则才能通过人工补译。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=10,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    target_entry: JsonObject = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        if original_lines == ["こんにちは"]:
            target_path = location_path
            entry["translation_lines"] = ["こんにちは"]
            target_entry = {key: value for key, value in entry.items()}
            break
    assert export_report.status == "ok"
    assert target_path
    _ = pending_path.write_text(
        json.dumps({target_path: target_entry}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rejected_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )
    rules_text = json.dumps(
        {
            "position_rules": {
                target_path: {
                    "allowed_terms": ["こんにちは"],
                    "reason": "proper_noun",
                }
            },
            "structural_rules": [],
        },
        ensure_ascii=False,
    )
    validate_report = await service.validate_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    import_rules_report = await service.import_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    accepted_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert rejected_report.status == "error"
    assert "日文残留" in rejected_report.errors[0].message
    assert validate_report.status == "ok"
    assert import_rules_report.status == "ok"
    assert accepted_report.status == "ok"
    assert quality_report.summary["source_residual_rule_count"] == 1
    assert quality_report.summary["source_residual_count"] == 0
    assert quality_report.details["source_residual_items"] == []
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        residual_rules = await session.read_source_residual_rules()
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines == ["こんにちは"]
    assert residual_rules[0].rule_type == "position"
    assert residual_rules[0].location_path == target_path
    assert residual_rules[0].allowed_terms == ["こんにちは"]
    assert residual_rules[0].reason == "proper_noun"


@pytest.mark.asyncio
async def test_quality_report_treats_source_residual_as_error(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告把未放行的源文残留风险作为禁止写进游戏文件的问题。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    residual_path = ""
    residual_original_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if any(_contains_japanese_test_char(line) for line in original_lines):
            residual_path = location_path
            residual_original_lines = original_lines
            break
    assert residual_path

    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=residual_path,
                    item_type="short_text",
                    role=None,
                    original_lines=residual_original_lines,
                    source_line_paths=[],
                    translation_lines=residual_original_lines,
                )
            ]
        )

    report = await service.quality_report(game_title="テストゲーム")

    error_codes = {error.code for error in report.errors}
    warning_codes = {warning.code for warning in report.warnings}
    assert report.status == "error"
    assert "source_residual" in error_codes
    assert "source_residual" not in warning_codes
    assert report.summary["source_residual_count"] == 1


@pytest.mark.asyncio
async def test_quality_report_structural_source_residual_rule_is_line_scoped(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构性源文例外在原生质检中只遮蔽协议词，不放行显示文本残留。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    original_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        entry_original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if len(entry_original_lines) == 1:
            target_path = location_path
            original_lines = entry_original_lines
            break
    assert target_path
    rules_text = json.dumps(
        {
            "position_rules": {},
            "structural_rules": [
                {
                    "pattern": r"^(?P<protocol>なまえ):(?P<visible>.*)$",
                    "allowed_terms": ["なまえ"],
                    "check_group": "visible",
                    "reason": "protocol_label",
                }
            ],
        },
        ensure_ascii=False,
    )

    import_rules_report = await service.import_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=original_lines,
                    source_line_paths=[],
                    translation_lines=["なまえ:你好"],
                )
            ]
        )
    protocol_report = await service.quality_report(game_title="テストゲーム")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=original_lines,
                    source_line_paths=[],
                    translation_lines=["なまえ:なまえ"],
                )
            ]
        )
    leaked_report = await service.quality_report(game_title="テストゲーム")

    assert import_rules_report.status == "ok"
    assert protocol_report.summary["source_residual_count"] == 0
    assert leaked_report.summary["source_residual_count"] == 1


@pytest.mark.asyncio
async def test_quality_report_errors_on_corrupt_source_residual_rule(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告遇到损坏的源文残留例外规则时返回明确业务错误。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_source_residual_rules(
            [
                SourceResidualRuleRecord(
                    rule_id="structural:broken",
                    rule_type="structural",
                    pattern_text="[",
                    allowed_terms=["なまえ"],
                    check_group="visible",
                    reason="broken",
                )
            ]
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.quality_report(game_title="テストゲーム")

    assert report.status == "error"
    assert "source_residual_rules_invalid" in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_quality_report_ignores_stale_saved_translation_quality_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告把当前不可写的已保存译文作为必须处理的问题。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Removed.json/1/name",
                    item_type="short_text",
                    role=None,
                    original_lines=["こんにちは"],
                    source_line_paths=[],
                    translation_lines=["こんにちは"],
                )
            ]
        )

    report = await service.quality_report(game_title="テストゲーム")

    error_codes = {error.code for error in report.errors}
    warning_codes = {warning.code for warning in report.warnings}
    assert "source_residual" not in error_codes
    assert "stale_saved_translations" in error_codes
    assert "stale_saved_translations" not in warning_codes
    assert report.summary["stale_translation_count"] == 1
    assert report.summary["source_residual_count"] == 0
    assert report.details["source_residual_items"] == []


@pytest.mark.asyncio
async def test_quality_report_uses_command_setting_overrides(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """写入前质量报告使用本次命令传入的文本规则覆盖。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    residual_path = ""
    residual_original_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if any(_contains_japanese_test_char(line) for line in original_lines):
            residual_path = location_path
            residual_original_lines = original_lines
            break
    assert residual_path

    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=residual_path,
                    item_type="short_text",
                    role=None,
                    original_lines=residual_original_lines,
                    source_line_paths=[],
                    translation_lines=["中カ"],
                )
            ]
        )

    default_report = await service.quality_report(game_title="テストゲーム")
    override_report = await service.quality_report(
        game_title="テストゲーム",
        setting_overrides=SettingOverrides(source_residual_allowed_chars=["カ"]),
    )

    default_error_codes = {error.code for error in default_report.errors}
    override_error_codes = {error.code for error in override_report.errors}
    assert "source_residual" in default_error_codes
    assert "source_residual" not in override_error_codes
    assert default_report.summary["source_residual_count"] == 1
    assert override_report.summary["source_residual_count"] == 0


@pytest.mark.asyncio
async def test_agent_reports_error_on_stale_plugin_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 工具包把过期插件规则作为覆盖审计错误，同时不生成假文本。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
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
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    quality_report = await service.quality_report(game_title="テストゲーム")
    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    workspace_report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=tmp_path / "workspace",
        command_codes=None,
    )

    error_codes = {error.code for error in quality_report.errors}
    assert quality_report.summary["plugin_rule_count"] == 0
    assert quality_report.summary["stale_plugin_rule_count"] == 1
    assert "stale_plugin_rules" in error_codes
    assert export_report.status == "error"
    assert {error.code for error in export_report.errors} == {"stale_plugin_rules"}
    assert not pending_path.exists()
    assert workspace_report.status in {"ok", "warning"}
    assert workspace_report.summary["stale_plugin_rule_count"] == 1
    assert (tmp_path / "workspace" / "manifest.json").exists()


@pytest.mark.asyncio
async def test_manual_long_text_import_splits_overwide_lines(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """人工补译 long_text 入库前会按当前行宽配置自动拆短。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    setting_path = tmp_path / "setting.toml"
    setting_text = EXAMPLE_SETTING_PATH.read_text(encoding="utf-8")
    setting_text = setting_text.replace("long_text_line_width_limit = 26", "long_text_line_width_limit = 3")
    setting_text = setting_text.replace(
        'system_prompt_file = "prompts/text_translation_system.md"',
        f'system_prompt_file = "{(ROOT / "prompts" / "text_translation_system.md").as_posix()}"',
    )
    _ = setting_path.write_text(setting_text, encoding="utf-8")
    service = AgentToolkitService(game_registry=registry, setting_path=setting_path)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        if entry["item_type"] == "long_text":
            target_path = location_path
            entry["translation_lines"] = ["甲乙丙丁戊己庚辛"]
            _ = pending_path.write_text(
                json.dumps({target_path: entry}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            break

    import_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert export_report.status == "ok"
    assert target_path
    assert import_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines == ["甲乙丙", "丁戊己", "庚辛"]


@pytest.mark.parametrize(
    "translation_lines",
    [
        ["第一行", "第二行"],
        ["第一行\n第二行"],
        [r"第一行\n第二行"],
        ["译文：你好"],
        ["translation_lines: 你好"],
    ],
)
@pytest.mark.asyncio
async def test_manual_translation_import_rejects_text_structure_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
    translation_lines: list[str],
) -> None:
    """人工补译同样拒绝改动单字段结构或混入模型协议文本的译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if entry["item_type"] == "short_text" and not any("\n" in line or r"\n" in line for line in original_lines):
            target_path = location_path
            entry["translation_lines"] = cast(JsonValue, list(translation_lines))
            _ = pending_path.write_text(
                json.dumps({target_path: entry}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            break
    assert target_path

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "error"
    assert report.summary["imported_count"] == 0
    assert report.errors[0].code == "manual_translation_invalid"
    invalid_items = ensure_json_array(report.details["invalid_items"], "invalid_items")
    first_invalid = ensure_json_object(coerce_json_value(invalid_items[0]), "invalid_items[0]")
    assert first_invalid["location_path"] == target_path
    assert "message" in first_invalid
    assert "expected_real_line_break_count" in first_invalid


@pytest.mark.asyncio
async def test_manual_translation_import_reports_all_invalid_items_without_partial_write(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """人工补译导入一次报告所有坏条目，并且不保存任何部分成功结果。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    selected: JsonObject = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if entry["item_type"] != "short_text" or any("\n" in line or r"\n" in line for line in original_lines):
            continue
        entry["translation_lines"] = ["第一行\n第二行"] if not selected else ["译文：你好"]
        selected[location_path] = entry
        if len(selected) == 2:
            break
    assert len(selected) == 2
    _ = pending_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()

    invalid_items = ensure_json_array(report.details["invalid_items"], "invalid_items")
    assert report.status == "error"
    assert report.summary["imported_count"] == 0
    assert len(invalid_items) == 2
    assert translated_items == []
    assert any(
        ensure_json_object(coerce_json_value(item), "invalid_item")["actual_real_line_break_count"] == 1
        for item in invalid_items
    )


@pytest.mark.asyncio
async def test_export_quality_fix_template_collects_repairable_items(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量修复模板会从报告问题导出标准修复表并预填当前译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    template_path = tmp_path / "quality-fix-template.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    sorted_paths = sorted(payload)
    quality_error_path = sorted_paths[0]
    residual_path = ""
    for candidate_path in sorted_paths:
        if candidate_path == quality_error_path:
            continue
        candidate_entry = ensure_json_object(coerce_json_value(payload[candidate_path]), candidate_path)
        candidate_lines = ensure_json_array(candidate_entry["original_lines"], f"{candidate_path}.original_lines")
        if any(isinstance(line, str) and _contains_japanese_test_char(line) for line in candidate_lines):
            residual_path = candidate_path
            break
    assert residual_path
    placeholder_path = next(path for path in sorted_paths if path not in {quality_error_path, residual_path})
    quality_error_entry = ensure_json_object(coerce_json_value(payload[quality_error_path]), quality_error_path)
    residual_entry = ensure_json_object(coerce_json_value(payload[residual_path]), residual_path)
    residual_original_lines = [
        line
        for line in ensure_json_array(residual_entry["original_lines"], f"{residual_path}.original_lines")
        if isinstance(line, str)
    ]
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=residual_path,
                    item_type="short_text",
                    role=None,
                    original_lines=residual_original_lines,
                    source_line_paths=[],
                    translation_lines=residual_original_lines,
                ),
                TranslationItem(
                    location_path=placeholder_path,
                    item_type="long_text",
                    role=None,
                    original_lines=["こんにちは"],
                    source_line_paths=[],
                    translation_lines=[r"\C[4]甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                ),
            ]
        )
        run_record = await session.start_translation_run(
            total_extracted=len(sorted_paths),
            pending_count=len(sorted_paths),
            deduplicated_count=len(sorted_paths),
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path=quality_error_path,
                    item_type="short_text",
                    role=None,
                    original_lines=[
                        line
                        for line in ensure_json_array(
                            quality_error_entry["original_lines"],
                            f"{quality_error_path}.original_lines",
                        )
                        if isinstance(line, str)
                    ],
                    translation_lines=["候选译文"],
                    error_type="AI漏翻",
                    error_detail=["测试质量错误"],
                    model_response='{"translation_lines":["候选译文"]}',
                )
            ],
        )

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=template_path,
    )

    template = load_json_object(template_path)
    assert report.status == "ok"
    assert report.summary["quality_error_count"] == 1
    assert report.summary["quality_error_items_count"] == 1
    quality_error_category_counts = ensure_json_object(
        report.summary["quality_error_category_counts"],
        "quality_error_category_counts",
    )
    assert quality_error_category_counts["missing_translation"] == 1
    assert report.summary["source_residual_count"] == 1
    assert report.summary["placeholder_risk_count"] == 1
    assert report.summary["overwide_line_count"] == 1
    assert set(template) == {quality_error_path, residual_path, placeholder_path}
    quality_template = ensure_json_object(coerce_json_value(template[quality_error_path]), quality_error_path)
    placeholder_template = ensure_json_object(coerce_json_value(template[placeholder_path]), placeholder_path)
    assert quality_template["translation_lines"] == ["候选译文"]
    assert placeholder_template["translation_lines"] == [r"\C[4]甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"]
    categories = ensure_json_object(report.details["problem_categories_by_path"], "problem_categories_by_path")
    assert categories[placeholder_path] == ["placeholder_risk", "overwide_line"]


@pytest.mark.asyncio
async def test_quality_fix_template_restores_prefilled_model_placeholders(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """修复表会把模型临时译文里的程序占位符还原为游戏原始控制符。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    template_path = tmp_path / "quality-fix-template.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    target_original_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if any(r"\C[4]" in line for line in original_lines):
            target_path = location_path
            target_original_lines = original_lines
            break

    assert target_path
    async with await registry.open_game("テストゲーム") as session:
        run_record = await session.start_translation_run(
            total_extracted=len(payload),
            pending_count=len(payload),
            deduplicated_count=len(payload),
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path=target_path,
                    item_type="long_text",
                    role=None,
                    original_lines=target_original_lines,
                    translation_lines=[r"[RMMZ_TEXT_COLOR_4]强调[RMMZ_TEXT_COLOR_0]"],
                    error_type="控制符不匹配",
                    error_detail=["测试程序占位符还原"],
                    model_response='{"translation_lines":["[RMMZ_TEXT_COLOR_4]强调[RMMZ_TEXT_COLOR_0]"]}',
                )
            ],
        )

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=template_path,
    )

    template = load_json_object(template_path)
    exported_entry = ensure_json_object(coerce_json_value(template[target_path]), target_path)
    text_for_model_lines = ensure_json_array(exported_entry["text_for_model_lines"], f"{target_path}.text_for_model_lines")
    manual_fill_note = exported_entry["manual_fill_note"]
    assert report.status == "ok"
    assert exported_entry["translation_lines"] == [r"\C[4]强调\C[0]"]
    assert any(isinstance(line, str) and "[RMMZ_TEXT_COLOR_4]" in line for line in text_for_model_lines)
    assert isinstance(manual_fill_note, str)
    assert "text_for_model_lines 只供对照" in manual_fill_note
    assert "游戏原始控制符" in manual_fill_note


@pytest.mark.asyncio
async def test_reset_translations_validates_paths_before_deleting(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """重置译文命令遇到非法定位路径时不做部分删除。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    reset_path = tmp_path / "reset-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )
    payload = load_json_object(pending_path)
    target_path = next(iter(payload))
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=["こんにちは"],
                    source_line_paths=[],
                    translation_lines=["你好"],
                )
            ]
        )

    _ = reset_path.write_text(
        json.dumps({"location_paths": [target_path, "Missing.json/1"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    rejected_report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=reset_path,
    )
    async with await registry.open_game("テストゲーム") as session:
        paths_after_reject = await session.read_translation_location_paths()

    _ = reset_path.write_text(
        json.dumps({"location_paths": [target_path]}, ensure_ascii=False),
        encoding="utf-8",
    )
    accepted_report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=reset_path,
    )
    quality_report = await service.quality_report(game_title="テストゲーム")
    async with await registry.open_game("テストゲーム") as session:
        paths_after_accept = await session.read_translation_location_paths()

    assert rejected_report.status == "error"
    assert rejected_report.summary["reset_count"] == 0
    assert target_path in paths_after_reject
    assert accepted_report.status == "ok"
    assert accepted_report.summary["requested_count"] == 1
    assert accepted_report.summary["reset_count"] == 1
    assert target_path not in paths_after_accept
    pending_count = quality_report.summary["pending_count"]
    assert isinstance(pending_count, int)
    assert pending_count >= 1


@pytest.mark.asyncio
async def test_reset_translations_all_deletes_current_active_translation_cache(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """完整重译入口可以清除当前提取范围内全部已入库译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=2,
    )
    payload = load_json_object(pending_path)
    target_paths = list(payload)[:2]
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=["こんにちは"],
                    source_line_paths=[],
                    translation_lines=["你好"],
                )
                for target_path in target_paths
            ]
        )

    report = await service.reset_translations(game_title="テストゲーム", reset_all=True)
    quality_report = await service.quality_report(game_title="テストゲーム")
    async with await registry.open_game("テストゲーム") as session:
        remaining_paths = await session.read_translation_location_paths()

    assert report.status == "warning"
    assert report.summary["mode"] == "all"
    assert report.summary["reset_count"] == len(target_paths)
    requested_count = report.summary["requested_count"]
    assert isinstance(requested_count, int)
    assert requested_count >= len(target_paths)
    assert all(target_path not in remaining_paths for target_path in target_paths)
    pending_count = quality_report.summary["pending_count"]
    assert isinstance(pending_count, int)
    assert pending_count >= len(target_paths)


@pytest.mark.asyncio
async def test_validate_placeholder_rules_previews_roundtrip() -> None:
    """占位符规则校验报告展示模型可见文本与还原结果。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text='{"\\\\\\\\F\\\\[[^\\\\]]+\\\\]":"[CUSTOM_FACE_PORTRAIT_{index}]"}',
        sample_texts=[r"\F[GuideA]こんにちは\V[1]"],
    )

    assert report.status == "ok"
    assert report.summary["rule_count"] == 1
    samples = report.details["samples"]
    assert isinstance(samples, list)
    first_sample = samples[0]
    assert isinstance(first_sample, dict)
    assert first_sample["text_for_model"] == "[CUSTOM_FACE_PORTRAIT_1]こんにちは[RMMZ_VARIABLE_1]"
    assert first_sample["restored_text"] == r"\F[GuideA]こんにちは\V[1]"
    assert first_sample["roundtrip_ok"] is True


@pytest.mark.asyncio
async def test_validate_placeholder_rules_keeps_dialogue_after_joined_prefix_control() -> None:
    """校验预览能证明无分隔符控制符不会吞掉后面的英文正文。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps(
            {r"\\Shake": "[CUSTOM_PLUGIN_SHAKE_MARKER_{index}]"},
            ensure_ascii=False,
        ),
        sample_texts=[r"\ShakeStop this!!!"],
    )

    assert report.status == "ok"
    samples = report.details["samples"]
    assert isinstance(samples, list)
    first_sample = samples[0]
    assert isinstance(first_sample, dict)
    assert first_sample["text_for_model"] == "[CUSTOM_PLUGIN_SHAKE_MARKER_1]Stop this!!!"
    assert first_sample["restored_text"] == r"\ShakeStop this!!!"


@pytest.mark.asyncio
async def test_validate_placeholder_rules_blocks_bare_escape_match() -> None:
    """占位符规则不得误匹配裸 \\n、\\r、\\t 这类常见文本转义。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    unsafe_report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps(
            {r"(?i)\\N\d*": "[CUSTOM_PLUGIN_N_{index}]"},
            ensure_ascii=False,
        ),
        sample_texts=[r"\n"],
    )
    safe_report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps(
            {r"(?i)\\N\d+": "[CUSTOM_PLUGIN_N_{index}]"},
            ensure_ascii=False,
        ),
        sample_texts=[r"\N12"],
    )

    assert unsafe_report.status == "error"
    assert {error.code for error in unsafe_report.errors} == {"placeholder_rule_matches_common_escape"}
    assert safe_report.status == "ok"


@pytest.mark.asyncio
async def test_validate_placeholder_rules_warns_unicode_control_boundary() -> None:
    """占位符校验会提示非 ASCII 控制符边界，避免 Agent 按终端乱码猜测。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text="{}",
        sample_texts=[r"\F3[66」「ふーん……？」"],
    )

    warning_codes = {warning.code for warning in report.warnings}
    assert "unprotected_control_unicode_boundary" in warning_codes
    assert "U+300D" in report.warnings[0].message


@pytest.mark.asyncio
async def test_validate_event_command_rules_previews_direct_parameter_write_back(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令规则校验会预演 direct parameters[N] 命中项的回写。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    parameters[2] = "トップパラメータ"
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_event_command_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": [
                            "$['parameters'][2]",
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    assert report.status == "ok"
    preview = ensure_json_object(report.details["write_back_preview"], "write_back_preview")
    assert preview["status"] == "ok"
    assert preview["checked_item_count"] == 1


@pytest.mark.asyncio
async def test_validate_event_command_rules_reports_hits_per_rule(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令规则报告按规则组统计命中数量，避免把总命中数写到每条规则。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "357": [
                {
                    "match": {"0": "TestPlugin", "1": "Show"},
                    "paths": ["$['parameters'][3]['message']"],
                },
                {
                    "match": {"0": "ComplexPlugin", "1": "ShowWindow"},
                    "paths": [
                        "$['parameters'][3]['window']['title']",
                        "$['parameters'][3]['choices'][*]",
                    ],
                },
            ]
        },
        ensure_ascii=False,
    )

    report = await service.validate_event_command_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    assert report.status == "ok"
    rule_details = ensure_json_array(report.details["rules"], "rules")
    hit_counts = [
        ensure_json_object(coerce_json_value(raw_detail), f"rules[{index}]")["hit_count"]
        for index, raw_detail in enumerate(rule_details)
    ]
    assert hit_counts == [1, 3]


@pytest.mark.asyncio
async def test_quality_report_counts_errors_and_model_response(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告读取译文、质量错误和规则状态，输出阻断级错误摘要。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="アリス",
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=[r"\C[4]甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                )
            ]
        )
        run_record = await session.start_translation_run(
            total_extracted=3,
            pending_count=2,
            deduplicated_count=2,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path="CommonEvents.json/1/2",
                    item_type="array",
                    role=None,
                    original_lines=["はい", "いいえ"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["缺少键"],
                    model_response='{"bad": true}',
                )
            ],
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    assert report.status == "error"
    assert report.summary["quality_error_count"] == 1
    assert report.summary["model_response_error_count"] == 1
    assert report.summary["placeholder_risk_count"] == 1
    assert report.summary["overwide_line_count"] == 1
    assert report.details["error_type_counts"] == {"AI漏翻": 1}
    quality_error_items = ensure_json_array(report.details["quality_error_items"], "quality_error_items")
    placeholder_items = ensure_json_array(report.details["placeholder_risk_items"], "placeholder_risk_items")
    overwide_items = ensure_json_array(report.details["overwide_line_items"], "overwide_line_items")
    quality_error_detail = ensure_json_object(quality_error_items[0], "quality_error_items[0]")
    placeholder_detail = ensure_json_object(placeholder_items[0], "placeholder_risk_items[0]")
    overwide_detail = ensure_json_object(overwide_items[0], "overwide_line_items[0]")
    assert quality_error_detail["location_path"] == "CommonEvents.json/1/2"
    assert quality_error_detail["error_type"] == "AI漏翻"
    assert placeholder_detail["location_path"] == "CommonEvents.json/1/0"
    assert overwide_detail["location_path"] == "CommonEvents.json/1/0"
    assert overwide_detail["line_width"] == 30


@pytest.mark.asyncio
async def test_quality_report_flags_internal_placeholder_leak(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告必须拦截译文里的项目内部占位符。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="アリス",
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["你好[RMMZ_TEXT_COLOR_0]"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    assert report.status == "error"
    assert report.summary["placeholder_risk_count"] == 1
    placeholder_items = ensure_json_array(report.details["placeholder_risk_items"], "placeholder_risk_items")
    placeholder_detail = ensure_json_object(placeholder_items[0], "placeholder_risk_items[0]")
    assert placeholder_detail["location_path"] == "CommonEvents.json/1/0"
    assert "译文残留项目内部占位符" in str(placeholder_detail["reason"])


@pytest.mark.asyncio
async def test_quality_report_accepts_saved_short_text_real_line_breaks(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告复查已保存译文时允许游戏文件需要的真实换行。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/description",
                    item_type="short_text",
                    role=None,
                    original_lines=["説明\n本文"],
                    source_line_paths=["Items.json/1/description"],
                    translation_lines=["说明\n正文"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    assert report.summary["placeholder_risk_count"] == 0


@pytest.mark.asyncio
async def test_quality_report_flags_multiline_short_text_overwide_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告按单值文本的实际显示行检查 Note 标签超宽风险。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_value = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    items = ensure_json_array(raw_value, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:説明\n原文>"
    _ = items_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [
                NoteTagTextRuleRecord(
                    file_name="Items.json",
                    tag_names=["拡張説明"],
                )
            ]
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/note/拡張説明",
                    item_type="short_text",
                    original_lines=["説明\n原文"],
                    translation_lines=["说明\n甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    overwide_items = ensure_json_array(report.details["overwide_line_items"], "overwide_line_items")
    overwide_detail = ensure_json_object(overwide_items[0], "overwide_line_items[0]")
    assert report.summary["overwide_line_count"] == 1
    assert overwide_detail["location_path"] == "Items.json/1/note/拡張説明"
    assert overwide_detail["item_type"] == "short_text"
    assert overwide_detail["line_index"] == 1
    assert overwide_detail["line_width"] == 30


@pytest.mark.asyncio
async def test_quality_report_flags_literal_line_break_short_text_overwide_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告会把字面量反斜杠 n 也当作游戏显示换行检查行宽。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_value = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    items = ensure_json_array(raw_value, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = r"<拡張説明:説明\n原文>"
    _ = items_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [
                NoteTagTextRuleRecord(
                    file_name="Items.json",
                    tag_names=["拡張説明"],
                )
            ]
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/note/拡張説明",
                    item_type="short_text",
                    original_lines=[r"説明\n原文"],
                    translation_lines=[r"说明\n甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    overwide_items = ensure_json_array(report.details["overwide_line_items"], "overwide_line_items")
    overwide_detail = ensure_json_object(overwide_items[0], "overwide_line_items[0]")
    assert report.summary["overwide_line_count"] == 1
    assert overwide_detail["location_path"] == "Items.json/1/note/拡張説明"
    assert overwide_detail["item_type"] == "short_text"
    assert overwide_detail["line_index"] == 1
    assert overwide_detail["line_width"] == 30


@pytest.mark.asyncio
async def test_quality_report_allows_original_overwide_short_text_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """原文同一显示行本来很长时，单值文本不按普通对话框宽度误报。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_value = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    items = ensure_json_array(raw_value, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:説明\n原原原原原原原原原原原原原原原原原原原原原原原原原原原原原原>"
    _ = items_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [
                NoteTagTextRuleRecord(
                    file_name="Items.json",
                    tag_names=["拡張説明"],
                )
            ]
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/note/拡張説明",
                    item_type="short_text",
                    original_lines=["説明\n原原原原原原原原原原原原原原原原原原原原原原原原原原原原原原"],
                    translation_lines=["说明\n甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    assert report.summary["overwide_line_count"] == 0


@pytest.mark.asyncio
async def test_quality_report_flags_saved_short_text_structure_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告会拦截已保存译文中改动单字段结构的问题。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/description",
                    item_type="short_text",
                    original_lines=["アイテム説明"],
                    translation_lines=["说明\n额外一行"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    error_codes = {error.code for error in report.errors}
    text_structure_items = ensure_json_array(report.details["text_structure_items"], "text_structure_items")
    text_structure_detail = ensure_json_object(text_structure_items[0], "text_structure_items[0]")
    assert "text_structure" in error_codes
    assert report.summary["text_structure_count"] == 1
    assert text_structure_detail["location_path"] == "Items.json/1/description"
