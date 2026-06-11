"""Agent doctor 诊断业务契约测试。"""

from __future__ import annotations

from tests.agent_toolkit_contract_fixtures import *
from app.native_scope_index import collect_native_plugin_config_scope_hash

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
    assert report.summary["llm_check_performed"] is True
    assert report.summary["llm_connection_status"] == "ok"
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
    assert report.summary["llm_check_performed"] is False
    assert report.summary["llm_connection_status"] == "skipped"
@pytest.mark.asyncio
async def test_doctor_reports_missing_standard_data_file(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """doctor 会把目标游戏标准 data 文件缺失报告为错误。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    (minimal_game_dir / "data" / "Animations.json").unlink()
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.doctor(game_title="テストゲーム", check_llm=False)

    assert report.status == "error"
    game_errors = [error.message for error in report.errors if error.code == "game"]
    assert game_errors
    assert "Animations.json" in game_errors[0]
@pytest.mark.asyncio
async def test_doctor_respects_reviewed_empty_rule_state_until_scope_changes(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """doctor 能区分规则未处理、已确认空结果和输入范围变化后的过期空结果。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_rule_review_state(
            rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
            scope_hash=collect_native_plugin_config_scope_hash(
                game_data=game_data,
                text_rules=text_rules,
            ),
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
    changed_report = await service.doctor(game_title="テストゲーム", check_llm=False)

    fresh_warning_codes = {warning.code for warning in fresh_report.warnings}
    changed_warning_codes = {warning.code for warning in changed_report.warnings}
    assert "plugin_rules" not in fresh_warning_codes
    assert "event_command_rules" not in fresh_warning_codes
    assert "note_tag_rules" not in fresh_warning_codes
    assert fresh_report.summary["plugin_rules_reviewed_empty"] is True
    assert fresh_report.summary["event_command_rules_reviewed_empty"] is True
    assert fresh_report.summary["note_tag_rules_reviewed_empty"] is True
    assert changed_report.summary["event_command_rules_reviewed_empty"] is True
    assert changed_report.summary["event_command_rules_review_state_stale"] is False
    assert "event_command_rules_review_state_stale" not in changed_warning_codes
@pytest.mark.asyncio
async def test_doctor_reports_mv_virtual_namebox_rule_state(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """doctor 会报告 MV 虚拟名字框规则导入和空规则确认状态。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    missing_report = await service.doctor(game_title="MVテストゲーム", check_llm=False)
    empty_report = await service.import_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text='{"rules":[]}',
        confirm_empty=True,
    )
    confirmed_report = await service.doctor(game_title="MVテストゲーム", check_llm=False)

    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_events.append(
        {
            "id": 99,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["新しい候補："]},
                {"code": 401, "parameters": ["本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    changed_report = await service.doctor(game_title="MVテストゲーム", check_llm=False)

    missing_warning_codes = {warning.code for warning in missing_report.warnings}
    confirmed_warning_codes = {warning.code for warning in confirmed_report.warnings}
    changed_warning_codes = {warning.code for warning in changed_report.warnings}
    assert empty_report.status == "warning"
    assert "mv_virtual_namebox_rules" in missing_warning_codes
    assert missing_report.summary["mv_virtual_namebox_rule_count"] == 0
    assert missing_report.summary["mv_virtual_namebox_rules_reviewed_empty"] is False
    assert "mv_virtual_namebox_rules" not in confirmed_warning_codes
    assert confirmed_report.summary["mv_virtual_namebox_rule_count"] == 0
    assert confirmed_report.summary["mv_virtual_namebox_rules_reviewed_empty"] is True
    assert confirmed_report.summary["mv_virtual_namebox_rules_review_state_stale"] is False
    assert changed_report.summary["mv_virtual_namebox_rules_reviewed_empty"] is True
    assert changed_report.summary["mv_virtual_namebox_rules_review_state_stale"] is False
    assert "mv_virtual_namebox_rules_review_state_stale" not in changed_warning_codes
@pytest.mark.asyncio
async def test_current_game_reports_invalid_saved_placeholder_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前数据库里的无效普通占位符规则必须在公开命令中显式报错。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_placeholder_rules(
            [
                PlaceholderRuleRecord(
                    pattern_text=r"(?a:@PLUGIN\[[^\]]+\])",
                    placeholder_template="[CUSTOM_PLUGIN_MARKER_{index}]",
                )
            ]
        )

    doctor_report = await service.doctor(game_title="テストゲーム", check_llm=False)
    scope_report = await service.text_scope(game_title="テストゲーム")
    audit_report = await service.audit_coverage(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")

    for report in (doctor_report, scope_report, audit_report, quality_report):
        assert report.status == "error"
        assert "placeholder_rules_invalid" in {error.code for error in report.errors}
        assert "Rust fancy-regex" in report.errors[0].message
@pytest.mark.asyncio
async def test_current_game_reports_invalid_saved_mv_virtual_namebox_rules(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前数据库里的无效 MV 虚拟名字框规则必须在公开命令中显式报错。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("MVテストゲーム") as session:
        await session.replace_mv_virtual_namebox_rules(
            [
                MvVirtualNameboxRuleRecord(
                    rule_order=0,
                    rule_name="bad-ascii-flag",
                    pattern_text=r"(?a:(?P<speaker>[^:：]+))[:：](?P<body>.*)",
                    speaker_group="speaker",
                    body_group="body",
                    speaker_policy="translate",
                    render_template="{speaker}：{body}",
                )
            ]
        )

    doctor_report = await service.doctor(game_title="MVテストゲーム", check_llm=False)
    scope_report = await service.text_scope(game_title="MVテストゲーム")
    audit_report = await service.audit_coverage(game_title="MVテストゲーム")
    quality_report = await service.quality_report(game_title="MVテストゲーム")

    for report in (doctor_report, scope_report, audit_report, quality_report):
        assert report.status == "error"
        assert "mv_virtual_namebox_rules_invalid" in {error.code for error in report.errors}
        assert "Rust fancy-regex" in report.errors[0].message
@pytest.mark.asyncio
async def test_current_game_reports_saved_mv_virtual_namebox_non_python_named_groups(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 虚拟名字框规则使用非 Python 命名分组时也必须返回稳定错误码。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("MVテストゲーム") as session:
        await session.replace_mv_virtual_namebox_rules(
            [
                MvVirtualNameboxRuleRecord(
                    rule_order=0,
                    rule_name="bad-named-group",
                    pattern_text=r"(?<speaker>[^:：]+)[:：](?<body>.*)",
                    speaker_group="speaker",
                    body_group="body",
                    speaker_policy="translate",
                    render_template="{speaker}：{body}",
                )
            ]
        )

    report = await service.text_scope(game_title="MVテストゲーム")

    assert report.status == "error"
    assert "mv_virtual_namebox_rules_invalid" in {error.code for error in report.errors}
    assert "Python re" in report.errors[0].message
