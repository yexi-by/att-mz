"""Agent 规则导入、规则审查和规则校验业务契约测试。"""

from __future__ import annotations

from tests.agent_toolkit_contract_fixtures import *
from tests.current_text_fact_scope import rebuild_current_text_fact_scope_for_test

from app.application.flow_gate import count_note_tag_rule_candidates
from app.event_command_text import (
    build_event_command_rule_records_from_import_shape,
    parse_event_command_rule_import_text,
)
from app.note_tag_text import parse_note_tag_rule_import_text
from app.native_note_tag_scan import collect_native_note_tag_candidate_details
from app.native_placeholder_scan import (
    collect_native_placeholder_candidate_details,
    count_uncovered_placeholder_candidate_details,
)
from app.native_scope_index import collect_native_plugin_config_scope_hash
from app.persistence import TargetGameSession
from app.persistence.records import TextFactRecord
from app.plugin_text import parse_plugin_rule_import_text
from app.plugin_source_text.native_scan import (
    PLUGIN_SOURCE_RUNTIME_SCAN_PARSER_CONTRACT_VERSION,
    PLUGIN_SOURCE_RUNTIME_SCAN_RUST_CONTRACT_VERSION,
)
from app.plugin_source_text.runtime_audit import PLUGIN_SOURCE_RUNTIME_AUDIT_CONTRACT_VERSION
from app.rmmz.mv_namebox import parse_mv_virtual_namebox_rule_import_text
from app.plugin_source_text.scanner import build_plugin_source_file_hash
from app.rmmz.schema import TranslationItem
from app.rmmz.text_rules import get_default_text_rules
from app.source_residual import parse_source_residual_rule_import_text
from app.agent_toolkit.services.rule_identity import RuleFactProbe, resolve_current_rule_fact_hits
from app.text_facts import (
    read_current_text_fact_records,
    read_current_text_fact_scope,
    text_fact_record_to_translation_item,
)


def _json_int_for_assert(value: object, label: str) -> int:
    """把报告 JSON 动态值收窄成整数，供类型检查稳定断言。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{label} 必须是整数")
    return value


def _workflow_gate_source_branch(report: AgentReport, source_branch: str) -> JsonObject:
    """读取质量报告中的 Rust source branch gate 摘要。"""
    workflow_gate = ensure_json_object(report.details["workflow_gate"], "workflow_gate")
    source_branches = ensure_json_object(workflow_gate["source_branches"], "workflow_gate.source_branches")
    return ensure_json_object(
        source_branches[source_branch],
        f"workflow_gate.source_branches.{source_branch}",
    )


def test_rule_review_no_longer_exports_python_scope_hash_helpers() -> None:
    """scope hash 只能来自 Rust/native 事实源。"""
    import app.rule_review as rule_review

    assert not hasattr(rule_review, "plugin_rule_scope_hash")
    assert not hasattr(rule_review, "note_tag_rule_scope_hash_for_candidates")


def test_plugin_rule_import_accepts_integer_string_index() -> None:
    """插件规则 plugin_index 可以用整数字符串表达。"""
    import_file = parse_plugin_rule_import_text(
        """
        [
          {
            "plugin_index": "0",
            "plugin_name": 123,
            "paths": [1]
          }
        ]
        """
    )

    assert import_file[0].plugin_index == 0
    assert import_file[0].plugin_name == "123"
    assert import_file[0].paths == ["1"]


def test_plugin_rule_import_rejects_boolean_index() -> None:
    """插件规则 plugin_index 不能用布尔值表达。"""
    with pytest.raises(Exception) as error_info:
        _ = parse_plugin_rule_import_text(
            """
            [
              {
                "plugin_index": true,
                "plugin_name": "Plugin",
                "paths": ["parameters/name"]
              }
            ]
            """
        )

    assert "bool" in str(error_info.value)


def test_event_command_rule_import_normalizes_match_and_paths() -> None:
    """事件指令规则中的 match 值和路径可以用整数表达字符串。"""
    import_file = parse_event_command_rule_import_text(
        """
        {
          "357": [
            {
              "match": {"0": 123},
              "paths": [1]
            }
          ]
        }
        """
    )

    specs = import_file["357"]
    assert specs[0].match == {"0": "123"}
    assert specs[0].paths == ["1"]


def test_event_command_rule_import_rejects_boolean_match_value() -> None:
    """事件指令规则中的 match 值不能用布尔值表达。"""
    with pytest.raises(Exception) as error_info:
        _ = parse_event_command_rule_import_text(
            """
            {
              "357": [
                {
                  "match": {"0": true},
                  "paths": ["0"]
                }
              ]
            }
            """
        )

    assert "bool" in str(error_info.value)


def test_event_command_rule_import_reports_invalid_match_index() -> None:
    """事件指令规则中的 match 键必须报告为参数索引错误。"""
    import_file = parse_event_command_rule_import_text(
        """
        {
          "357": [
            {
              "match": {"x": "abc"},
              "paths": ["0"]
            }
          ]
        }
        """
    )

    with pytest.raises(ValueError, match="match 的键必须是参数索引"):
        _ = build_event_command_rule_records_from_import_shape(import_file=import_file)


def test_note_tag_rule_import_normalizes_integer_fields() -> None:
    """Note 标签规则导入中的文本字段允许整数表达。"""
    import_file = parse_note_tag_rule_import_text(json.dumps({123: [456]}, ensure_ascii=False))

    assert import_file == {"123": ["456"]}


def test_note_tag_rule_import_rejects_boolean_tag_name() -> None:
    """Note 标签规则导入中的布尔标签名无效。"""
    with pytest.raises(Exception) as error_info:
        _ = parse_note_tag_rule_import_text(json.dumps({"Items.json": [True]}, ensure_ascii=False))

    assert "bool" in str(error_info.value)


def test_source_residual_rule_import_normalizes_integer_fields() -> None:
    """源文残留规则导入中的文本字段允许整数表达。"""
    import_file = parse_source_residual_rule_import_text(
        json.dumps(
            {
                "position_rules": {
                    123: {
                        "allowed_terms": [456],
                        "reason": 789,
                    }
                },
                "structural_rules": [
                    {
                        "pattern": "(?P<word>abc)",
                        "allowed_terms": [123],
                        "check_group": 456,
                        "reason": 789,
                    }
                ],
            },
            ensure_ascii=False,
        )
    )

    assert import_file.position_rules["123"].allowed_terms == ["456"]
    assert import_file.position_rules["123"].reason == "789"
    assert import_file.structural_rules[0].allowed_terms == ["123"]
    assert import_file.structural_rules[0].check_group == "456"
    assert import_file.structural_rules[0].reason == "789"


def test_source_residual_rule_import_rejects_boolean_reason() -> None:
    """源文残留规则导入中的布尔原因无效。"""
    with pytest.raises(Exception) as error_info:
        _ = parse_source_residual_rule_import_text(
            json.dumps(
                {
                    "position_rules": {
                        "Map001.json/1/0/0": {
                            "allowed_terms": ["abc"],
                            "reason": True,
                        }
                    },
                    "structural_rules": [],
                },
                ensure_ascii=False,
            )
        )

    assert "bool" in str(error_info.value)


def test_mv_namebox_rule_import_normalizes_integer_fields() -> None:
    """MV 虚拟名字框规则导入中的文本字段允许整数表达。"""
    records = parse_mv_virtual_namebox_rule_import_text(
        json.dumps(
            {
                "rules": [
                    {
                        "name": 123,
                        "pattern": r"^(?P<speaker>[^：]+)：(?P<body>.*)$",
                        "speaker_group": "speaker",
                        "speaker_policy": "translate",
                        "render_template": "{speaker}：{body}",
                        "body_group": "body",
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    assert records[0].rule_name == "123"


def test_mv_namebox_rule_import_rejects_boolean_name() -> None:
    """MV 虚拟名字框规则导入中的布尔规则名无效。"""
    with pytest.raises(Exception) as error_info:
        _ = parse_mv_virtual_namebox_rule_import_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "name": True,
                            "pattern": r"^(?P<speaker>[^：]+)：(?P<body>.*)$",
                            "speaker_group": "speaker",
                            "speaker_policy": "translate",
                            "render_template": "{speaker}：{body}",
                            "body_group": "body",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )

    assert "bool" in str(error_info.value)


async def _translation_item_from_text_fact_for_test(
    session: TargetGameSession,
    fact: TextFactRecord,
) -> TranslationItem:
    """用当前文本索引定位记录构造测试译文项。"""
    index_records = await session.read_text_index_items_by_paths([fact.location_path])
    index_record = index_records[0] if index_records else None
    return text_fact_record_to_translation_item(fact, index_record=index_record)

@pytest.mark.asyncio
async def test_agent_translation_source_load_skips_writable_copies_by_default(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 只读翻译源加载默认不读取插件源码，也不构造大型可写副本。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = _AgentToolkitServiceProbe(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    async with await registry.open_game("テストゲーム") as session:
        game_data = await service.load_translation_source_for_test(session)
        writable_game_data = await service.load_translation_source_for_test(
            session,
            include_writable_copies=True,
        )
        plugin_source_game_data = await service.load_translation_source_for_test(
            session,
            include_plugin_source_files=True,
        )

    assert game_data.data
    assert game_data.plugin_source_files == {}
    assert game_data.writable_data == {}
    assert game_data.writable_plugins_js == []
    assert game_data.writable_plugin_source_files == {}
    assert writable_game_data.writable_data
    assert writable_game_data.writable_plugins_js
    assert set(plugin_source_game_data.plugin_source_files) == {"ComplexPlugin.js", "TestPlugin.js"}
@pytest.mark.asyncio
async def test_import_empty_plugin_rules_requires_explicit_empty_confirmation(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件规则为空时默认报错；显式确认后允许保存当前插件范围的空结果。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
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
        await write_current_translation_items_for_test(session,
            [
                TranslationItem(
                    location_path="plugins.js/0/Message",
                    item_type="short_text",
                    original_lines=["プラグイン台詞"],
                    translation_lines=["插件译文"],
                )
            ]
        )

    with pytest.raises(RuntimeError, match="--confirm-empty"):
        _ = await handler.import_plugin_rules(game_title="テストゲーム", input_path=empty_rules_path)
    summary = await handler.import_plugin_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
        confirm_empty=True,
    )
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        state = await session.read_rule_review_state(rule_domain=PLUGIN_TEXT_RULE_DOMAIN)

    assert summary.imported_plugin_count == 0
    assert summary.imported_rule_count == 0
    assert summary.deleted_translation_items == 1
    assert summary.deleted_translation_backup_path
    assert translated_items == []
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    text_rules = get_default_text_rules()
    assert state is not None
    assert state.scope_hash == collect_native_plugin_config_scope_hash(
        game_data=game_data,
        text_rules=text_rules,
    )
@pytest.mark.asyncio
@pytest.mark.usefixtures("app_home_with_example_setting")
async def test_import_plugin_rules_rejects_english_protocol_value_paths(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件规则导入会拒绝英文模式下只命中协议值的路径。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    rules_path = tmp_path / "plugin-rules.json"
    _ = rules_path.write_text(
        json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "VisiblePlugin",
                    "paths": ["$['parameters']['Enabled']"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())

    try:
        with pytest.raises(ValueError, match="没有命中玩家可见可翻译文本"):
            _ = await handler.import_plugin_rules(
                game_title="English Fixture Game",
                input_path=rules_path,
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_import_plugin_rules_uses_configured_text_rules(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件规则导入按当前配置判断命中文本，不能退回固定语言档案。"""
    configured_text_rules = TextRulesSetting(
        source_language="en",
        source_residual_label="英文",
        source_text_required_pattern="true",
        source_text_exclusion_profile="none",
        source_residual_segment_pattern="true",
    )

    def fake_load_setting(
        setting_path: str | Path | None = None,
        overrides: SettingOverrides | None = None,
        source_language: SourceLanguage = "ja",
    ) -> Setting:
        """返回带测试文本规则的配置。"""
        target_setting_path = EXAMPLE_SETTING_PATH if setting_path is None else Path(setting_path)
        setting = load_setting(target_setting_path, overrides=overrides, source_language=source_language)
        return setting.model_copy(update={"text_rules": configured_text_rules})

    monkeypatch.setattr("app.application.handler.load_setting", fake_load_setting)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    rules_path = tmp_path / "plugin-rules.json"
    _ = rules_path.write_text(
        json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "VisiblePlugin",
                    "paths": ["$['parameters']['Enabled']"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())

    try:
        summary = await handler.import_plugin_rules(
            game_title="English Fixture Game",
            input_path=rules_path,
        )
    finally:
        await handler.close()

    assert summary.imported_rule_count == 1


@pytest.mark.asyncio
async def test_import_plugin_rules_uses_native_plugin_config_context(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件规则导入前覆盖检查和旧译文清理消费 native 插件参数命中事实。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))

    def forbidden_old_record_builder(**_kwargs: object) -> list[PluginTextRuleRecord]:
        raise AssertionError("import-plugin-rules 必须消费 Rust 插件参数规则候选输出")

    monkeypatch.setattr(
        "app.application.handler.build_plugin_rule_records_from_import",
        forbidden_old_record_builder,
        raising=False,
    )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    old_rule = PluginTextRuleRecord(
        plugin_index=0,
        plugin_name="TestPlugin",
        plugin_hash=build_plugin_hash(game_data.plugins_js[0]),
        path_templates=["$['parameters']['Message']"],
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_text_rules([old_rule])
        await write_current_translation_items_for_test(session,
            [
                TranslationItem(
                    location_path="plugins.js/0/Message",
                    item_type="short_text",
                    original_lines=["プラグイン本文"],
                    translation_lines=["插件正文"],
                )
            ]
        )
    rules_path = tmp_path / "plugin-rules.json"
    _ = rules_path.write_text(
        json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Nested']['text']"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())

    summary = await handler.import_plugin_rules(game_title="テストゲーム", input_path=rules_path)
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        saved_rules = await session.read_plugin_text_rules()

    assert summary.imported_plugin_count == 1
    assert summary.imported_rule_count == 1
    assert summary.deleted_translation_items == 1
    assert summary.deleted_translation_backup_path
    assert translated_items == []
    assert [rule.path_templates for rule in saved_rules] == [["$['parameters']['Nested']['text']"]]


@pytest.mark.asyncio
async def test_import_plugin_rules_deletes_only_stale_fact_id_for_same_path(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公开插件规则导入按 fact_id 删除同路径旧译文，不能按 prefix 删除。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(game_data.plugins_js[0]),
                    path_templates=[
                        "$['parameters']['Message']",
                        "$['parameters']['Nested']['text']",
                    ],
                )
            ]
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        scope = await read_current_text_fact_scope(session)
        facts = await read_current_text_fact_records(session, limit=None)
        current_fact = next(
            fact
            for fact in facts
            if fact.domain == "plugin_config"
            and fact.location_path == "plugins.js/0/Message"
            and fact.translatable_text == "プラグイン本文"
        )
        current_fact_id = current_fact.fact_id
        stale_fact = type(current_fact)(
            fact_id=f"{current_fact.fact_id}:stale",
            schema_version=current_fact.schema_version,
            domain=current_fact.domain,
            location_path=current_fact.location_path,
            source_file=current_fact.source_file,
            source_type=current_fact.source_type,
            item_type=current_fact.item_type,
            role=current_fact.role,
            selector=current_fact.selector,
            raw_text="古いプラグイン本文",
            visible_text="古いプラグイン本文",
            translatable_text="古いプラグイン本文",
            raw_hash=f"{current_fact.raw_hash}:stale",
            visible_hash=f"{current_fact.visible_hash}:stale",
            translatable_hash=f"{current_fact.translatable_hash}:stale",
            scope_key=current_fact.scope_key,
        )
        await session.replace_text_facts(scope=scope, facts=[*facts, stale_fact])
        current_item = await _translation_item_from_text_fact_for_test(session, current_fact)
        current_item.translation_lines = ["当前插件正文"]
        stale_item = await _translation_item_from_text_fact_for_test(session, stale_fact)
        stale_item.translation_lines = ["旧插件正文"]
        await session.write_translation_items([current_item, stale_item])

    async def forbidden_prefix_delete(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("规则导入不得按 location_path prefix 删除译文")

    monkeypatch.setattr(TargetGameSession, "delete_translation_items_by_prefixes", forbidden_prefix_delete)
    rules_path = tmp_path / "plugin-rules.json"
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
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())

    try:
        summary = await handler.import_plugin_rules(game_title="テストゲーム", input_path=rules_path)
    finally:
        await handler.close()

    async with await registry.open_game("テストゲーム") as session:
        remaining_items = await session.read_translated_items()

    assert summary.deleted_translation_items == 1
    assert {item.fact_id for item in remaining_items} == {current_fact_id}
@pytest.mark.asyncio
async def test_import_empty_event_command_rules_requires_explicit_empty_confirmation(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令规则为空时默认报错；显式确认后允许保存当前编码范围的空结果。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
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
        await write_current_translation_items_for_test(session,
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/4/parameters/3/message",
                    item_type="short_text",
                    original_lines=["プラグイン台詞"],
                    translation_lines=["事件指令译文"],
                )
            ]
        )

    with pytest.raises(RuntimeError, match="--confirm-empty"):
        _ = await handler.import_event_command_rules(
            game_title="テストゲーム",
            input_path=empty_rules_path,
        )
    summary = await handler.import_event_command_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
        confirm_empty=True,
        command_codes={357},
    )
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        state = await session.read_rule_review_state(rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN)

    game_data = await load_active_runtime_game_data(minimal_game_dir)
    assert summary.imported_rule_group_count == 0
    assert summary.imported_path_rule_count == 0
    assert summary.deleted_translation_items == 1
    assert summary.deleted_translation_backup_path
    assert translated_items == []
    assert state is not None
    assert state.scope_hash == event_command_rule_scope_hash_for_command_codes(
        game_data=game_data,
        command_codes=frozenset({357}),
    )
@pytest.mark.asyncio
async def test_import_empty_event_command_rules_records_cli_code_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令空规则确认使用 CLI 显式编码计算范围。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    empty_rules_path = tmp_path / "event-command-rules-empty.json"
    _ = empty_rules_path.write_text("{}\n", encoding="utf-8")
    game_data = await load_active_runtime_game_data(minimal_game_dir)

    _ = await handler.import_event_command_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
        confirm_empty=True,
        command_codes={999},
    )

    async with await registry.open_game("テストゲーム") as session:
        state = await session.read_rule_review_state(rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN)

    assert state is not None
    assert state.scope_hash == event_command_rule_scope_hash_for_command_codes(
        game_data=game_data,
        command_codes=frozenset({999}),
    )


@pytest.mark.asyncio
async def test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令规则导入清理旧译文时消费 native 命中前缀。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    stale_item = TranslationItem(
        location_path="CommonEvents.json/1/4/parameters/3/message",
        item_type="short_text",
        original_lines=["プラグイン台詞"],
        translation_lines=["旧事件指令译文"],
    )
    async with await registry.open_game("テストゲーム") as session:
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
        await write_current_translation_items_for_test(session, [stale_item])

    rules_path = tmp_path / "event-command-rules.json"
    _ = rules_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {"0": "ComplexPlugin", "1": "ShowWindow"},
                        "paths": [
                            "$['parameters'][3]['window']['title']",
                            "$['parameters'][3]['choices'][*]",
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def forbidden_iter_all_commands(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("事件指令规则导入必须消费 native hit details")

    def forbidden_python_prefix_builder(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("事件指令规则导入必须消费 native command prefixes")

    monkeypatch.setattr("app.event_command_text.importer.iter_all_commands", forbidden_iter_all_commands)
    monkeypatch.setattr(
        TranslationHandler,
        "_event_command_rule_prefixes",
        forbidden_python_prefix_builder,
        raising=False,
    )
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())

    try:
        summary = await handler.import_event_command_rules(
            game_title="テストゲーム",
            input_path=rules_path,
        )
    finally:
        await handler.close()

    async with await registry.open_game("テストゲーム") as session:
        remaining_paths = {item.location_path for item in await session.read_translated_items()}
        imported_rules = await session.read_event_command_text_rules()

    assert summary.imported_rule_group_count == 1
    assert summary.imported_path_rule_count == 2
    assert summary.deleted_translation_items == 1
    assert summary.deleted_translation_backup_path
    assert stale_item.location_path not in remaining_paths
    assert imported_rules[0].command_code == 357
    assert set(imported_rules[0].path_templates) == {
        "$['parameters'][3]['window']['title']",
        "$['parameters'][3]['choices'][*]",
    }


@pytest.mark.asyncio
async def test_import_event_command_rules_deletes_only_stale_fact_id_for_same_path(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公开事件指令规则导入按 fact_id 删除同路径旧译文，不能按 prefix 删除。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[
                        EventCommandParameterFilter(index=0, value="TestPlugin"),
                        EventCommandParameterFilter(index=1, value="Show"),
                    ],
                    path_templates=[
                        "$['parameters'][3]['message']",
                        "$['parameters'][3]['missing']",
                    ],
                )
            ]
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        scope = await read_current_text_fact_scope(session)
        facts = await read_current_text_fact_records(session, limit=None)
        current_fact = next(
            fact
            for fact in facts
            if fact.domain == "event_command"
            and fact.location_path == "CommonEvents.json/1/4/parameters/3/message"
            and fact.translatable_text == "プラグイン台詞"
        )
        current_fact_id = current_fact.fact_id
        stale_fact = type(current_fact)(
            fact_id=f"{current_fact.fact_id}:stale",
            schema_version=current_fact.schema_version,
            domain=current_fact.domain,
            location_path=current_fact.location_path,
            source_file=current_fact.source_file,
            source_type=current_fact.source_type,
            item_type=current_fact.item_type,
            role=current_fact.role,
            selector=current_fact.selector,
            raw_text="古いプラグイン台詞",
            visible_text="古いプラグイン台詞",
            translatable_text="古いプラグイン台詞",
            raw_hash=f"{current_fact.raw_hash}:stale",
            visible_hash=f"{current_fact.visible_hash}:stale",
            translatable_hash=f"{current_fact.translatable_hash}:stale",
            scope_key=current_fact.scope_key,
        )
        await session.replace_text_facts(scope=scope, facts=[*facts, stale_fact])
        current_item = await _translation_item_from_text_fact_for_test(session, current_fact)
        current_item.translation_lines = ["当前事件指令译文"]
        stale_item = await _translation_item_from_text_fact_for_test(session, stale_fact)
        stale_item.translation_lines = ["旧事件指令译文"]
        await session.write_translation_items([current_item, stale_item])

    async def forbidden_prefix_delete(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("规则导入不得按 location_path prefix 删除译文")

    monkeypatch.setattr(TargetGameSession, "delete_translation_items_by_prefixes", forbidden_prefix_delete)
    rules_path = tmp_path / "event-command-rules.json"
    _ = rules_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {"0": "TestPlugin", "1": "Show"},
                        "paths": ["$['parameters'][3]['message']"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())

    try:
        summary = await handler.import_event_command_rules(
            game_title="テストゲーム",
            input_path=rules_path,
        )
    finally:
        await handler.close()

    async with await registry.open_game("テストゲーム") as session:
        remaining_items = await session.read_translated_items()

    assert summary.deleted_translation_items == 1
    assert {item.fact_id for item in remaining_items} == {current_fact_id}
@pytest.mark.asyncio
async def test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签规则导入清理旧译文时，只读取旧规则文件前缀。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    empty_rules_path = tmp_path / "note-tag-rules-empty.json"
    _ = empty_rules_path.write_text("{}\n", encoding="utf-8")
    missing_tag_path = "Items.json/1/note/MissingTag"
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["MissingTag"])]
        )
        await insert_invalid_fact_translation_row_for_test(
            session,
            fact_id="invalid-current-note-tag:missing-tag",
            location_path=missing_tag_path,
            item_type="short_text",
            role=None,
            original_lines=["古いタグ"],
            source_line_paths=[missing_tag_path],
            translation_lines=["待清理标签"],
        )

    async def forbidden_full_translation_read(_self: TargetGameSession) -> list[TranslationItem]:
        raise AssertionError("Note 标签规则导入不能全量读取已保存译文")

    async def forbidden_path_delete(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("Note 标签规则导入不得按 location_path 删除译文")

    monkeypatch.setattr(TargetGameSession, "read_translated_items", forbidden_full_translation_read)
    monkeypatch.setattr(TargetGameSession, "delete_translation_items_by_paths", forbidden_path_delete)

    summary = await handler.import_note_tag_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
        confirm_empty=True,
    )

    async with await registry.open_game("テストゲーム") as session:
        remaining_paths = {
            item.location_path
            for item in await session.read_translated_items_by_prefixes(["Items.json/"])
        }
        state = await session.read_rule_review_state(rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN)

    game_data = await load_active_runtime_game_data(minimal_game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    assert summary.imported_file_count == 0
    assert summary.imported_tag_count == 0
    assert summary.deleted_translation_items == 1
    assert missing_tag_path not in remaining_paths
    assert state is not None
    assert state.scope_hash == note_tag_rule_scope_hash_for_text_rules(
        game_data=game_data,
        text_rules=TextRules.from_setting(setting.text_rules),
    )


@pytest.mark.asyncio
async def test_import_note_tag_rules_keeps_same_file_non_note_translation_when_rules_empty(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """导入空 Note 规则只清理旧 Note 规则译文，不误删同文件普通字段译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    missing_tag_path = "Items.json/1/note/MissingTag"
    ordinary_path = "Items.json/1/name"
    ordinary_fact_id = "invalid-current-standard-data:item-name"
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["MissingTag"])]
        )
        await insert_invalid_fact_translation_row_for_test(
            session,
            fact_id="invalid-current-note-tag:missing-tag",
            location_path=missing_tag_path,
            item_type="short_text",
            role=None,
            original_lines=["古いタグ"],
            source_line_paths=[missing_tag_path],
            translation_lines=["待清理标签"],
        )
        await insert_invalid_fact_translation_row_for_test(
            session,
            fact_id=ordinary_fact_id,
            location_path=ordinary_path,
            item_type="short_text",
            role=None,
            original_lines=["回復薬"],
            source_line_paths=[ordinary_path],
            translation_lines=["回复药"],
        )

    report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    async with await registry.open_game("テストゲーム") as session:
        remaining_items = await session.read_translated_items()

    assert report.summary["deleted_translation_items"] == 1
    assert {item.fact_id for item in remaining_items} == {ordinary_fact_id}
@pytest.mark.asyncio
async def test_mv_virtual_namebox_rule_commands_validate_import_and_reject_mz(
    minimal_mv_game_dir: Path,
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 虚拟名字框规则只能用于 MV，并通过 CLI 服务校验后保存。"""
    mv_common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    mv_common_events = ensure_json_array(
        coerce_json_value(cast(object, json.loads(mv_common_events_path.read_text(encoding="utf-8")))),
        "CommonEvents.json",
    )
    mv_common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人："]},
                {"code": 401, "parameters": ["本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _ = mv_common_events_path.write_text(json.dumps(mv_common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    candidates_path = tmp_path / "mv-namebox-candidates.json"

    export_report = await service.export_mv_virtual_namebox_candidates(
        game_title="MVテストゲーム",
        output_path=candidates_path,
    )
    validate_report = await service.validate_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )
    import_report = await service.import_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )
    mz_report = await service.validate_mv_virtual_namebox_rules(
        game_title="テストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )

    assert export_report.status in {"ok", "warning"}
    assert candidates_path.exists()
    candidates_payload = load_json_object(candidates_path)
    candidate_count = export_report.summary["candidate_count"]
    assert isinstance(candidate_count, int)
    assert candidate_count >= 1
    assert isinstance(candidates_payload["scope_hash"], str)
    assert isinstance(candidates_payload["speaker_requirements"], list)
    assert validate_report.status == "ok"
    assert validate_report.summary["rule_count"] == 1
    assert validate_report.summary["matched_candidate_count"] == 1
    assert import_report.status == "ok"
    assert import_report.summary["rule_count"] == 1
    assert {error.code for error in mz_report.errors} == {"mv_virtual_namebox_rules_forbidden"}
    async with await registry.open_game("MVテストゲーム") as session:
        records = await session.read_mv_virtual_namebox_rules()
    assert len(records) == 1
    assert records[0].rule_name == "standalone-colon"


@pytest.mark.asyncio
async def test_mv_virtual_namebox_rule_commands_use_native_candidate_context(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 名字框三条命令必须消费 native 候选和命中事实。"""
    mv_common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    mv_common_events = ensure_json_array(
        coerce_json_value(cast(object, json.loads(mv_common_events_path.read_text(encoding="utf-8")))),
        "CommonEvents.json",
    )
    mv_common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人："]},
                {"code": 401, "parameters": ["本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _ = mv_common_events_path.write_text(json.dumps(mv_common_events, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    export_report = await service.export_mv_virtual_namebox_candidates(
        game_title="MVテストゲーム",
        output_path=tmp_path / "mv-namebox-candidates.json",
    )
    validate_report = await service.validate_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )
    import_report = await service.import_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )

    assert export_report.status in {"ok", "warning"}
    assert validate_report.status == "ok"
    assert validate_report.summary["matched_candidate_count"] == 1
    assert import_report.status == "ok"
    assert import_report.summary["matched_candidate_count"] == 1
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
async def test_validate_placeholder_rules_rejects_rust_unsupported_regex() -> None:
    """普通占位符规则不能先通过 Python 校验、再到 Rust 质检阶段失败。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps(
            {r"(?u:@PLUGIN\[[^\]]+\])": "[CUSTOM_PLUGIN_MARKER_{index}]"},
            ensure_ascii=False,
        ),
        sample_texts=["@PLUGIN[name]"],
    )

    assert report.status == "error"
    assert "pcre2_compile_error" in {error.code for error in report.errors}
    assert "PCRE2" in report.errors[0].message


@pytest.mark.asyncio
async def test_validate_placeholder_rules_normalizes_integer_template() -> None:
    """Agent 导入普通占位符规则时，整数模板按文本字段规范化。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps({r"\\Face\[[^\]]+\]": 123}, ensure_ascii=False),
        sample_texts=[r"\Face[Actor1]"],
    )

    assert report.status == "error"
    assert "placeholder_template_invalid" in {error.code for error in report.errors}
    assert "必须生成形如" in report.errors[0].message


@pytest.mark.asyncio
async def test_validate_placeholder_rules_rejects_boolean_template() -> None:
    """Agent 导入普通占位符规则时，布尔模板无效。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps({r"\\Face\[[^\]]+\]": True}, ensure_ascii=False),
        sample_texts=[r"\Face[Actor1]"],
    )

    assert report.status == "error"
    assert "placeholder_rules_invalid" in {error.code for error in report.errors}
    assert "bool" in report.errors[0].message


@pytest.mark.asyncio
async def test_validate_structured_placeholder_rules_rejects_rust_unsupported_regex(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化占位符规则导入前必须通过 PCRE2 预检。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "INLINE_LABEL",
                    "type": "paired_shell",
                    "pattern": r"(?u:(?P<prefix><label>))(?P<text>[^<]+)(?P<suffix></label>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "prefix": "[CUSTOM_INLINE_LABEL_PREFIX_{index}]",
                        "suffix": "[CUSTOM_INLINE_LABEL_SUFFIX_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=["<label>薬草</label>"],
    )

    assert report.status == "error"
    assert "pcre2_compile_error" in {error.code for error in report.errors}
    assert "PCRE2" in report.errors[0].message


@pytest.mark.asyncio
async def test_validate_structured_placeholder_rules_normalizes_integer_name(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 导入结构化占位符规则时，整数字段按文本字段规范化。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": 123,
                    "pattern": r"(?P<open><tag>)(?P<text>[^<]+)(?P<close></tag>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_TAG_OPEN_{index}]",
                        "close": "[CUSTOM_TAG_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=["<tag>薬草</tag>"],
    )

    assert report.status == "error"
    assert "structured_placeholder_rules_invalid" in {error.code for error in report.errors}
    assert "大写标识" in report.errors[0].message


@pytest.mark.asyncio
async def test_validate_structured_placeholder_rules_rejects_boolean_template(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 导入结构化占位符规则时，布尔模板无效。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "TAG",
                    "pattern": r"(?P<open><tag>)(?P<text>[^<]+)(?P<close></tag>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": True,
                        "close": "[CUSTOM_TAG_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=["<tag>薬草</tag>"],
    )

    assert report.status == "error"
    assert "structured_placeholder_rules_invalid" in {error.code for error in report.errors}
    assert "bool" in report.errors[0].message


@pytest.mark.asyncio
async def test_structured_placeholder_rule_commands_use_warm_text_index_coverage(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """warm index 可用时，结构化占位符规则命令复用当前索引覆盖结果。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)
    rules_text = '{"paired_shell_rules": []}'

    validate_report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=[],
    )
    scan_report = await service.scan_structured_placeholder_candidates(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    import_report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        confirm_empty=True,
    )

    assert validate_report.status in {"ok", "warning"}
    assert scan_report.status in {"ok", "warning"}
    assert import_report.status in {"ok", "warning"}
@pytest.mark.asyncio
async def test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行审计跨命令复用 AST 缓存，并在文件 hash 变化时重新扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "CacheSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source_path = plugin_source_dir / "CacheSource.js"
    _ = source_path.write_text("const Messages = { title: 'カテゴリ' };\n", encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    first_report = await service.audit_active_runtime(game_title="テストゲーム")
    assert first_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        cached_records = await session.read_plugin_source_runtime_scan_cache()
    cached_by_name = {record.file_name: record for record in cached_records}
    assert "CacheSource.js" in cached_by_name
    assert cached_by_name["CacheSource.js"].literals
    cached_file_count = len(cached_records)
    assert first_report.summary["active_runtime_scan_cache_input_record_count"] == 0
    assert first_report.summary["active_runtime_scan_cache_current_file_count"] == cached_file_count
    assert first_report.summary["active_runtime_scan_cache_hit_file_count"] == 0
    assert first_report.summary["active_runtime_scan_cache_miss_file_count"] == cached_file_count
    assert first_report.summary["active_runtime_scan_cache_rescan_file_count"] == cached_file_count

    from app.plugin_source_text import runtime_audit as runtime_audit_module
    scan_calls: list[tuple[str, ...]] = []

    def counting_scan(
        *,
        files: dict[str, str],
        active_file_names: frozenset[str],
    ) -> PluginSourceBatchTextScan:
        """记录真正进入当前运行 Rust-AST 扫描的文件。"""
        scan_calls.append(tuple(sorted(files)))
        return real_scan_plugin_source_runtime_files_text_strict(
            files=files,
            active_file_names=active_file_names,
        )

    def forbidden_translation_source_strict_scan(*args: object, **kwargs: object) -> PluginSourceBatchTextScan:
        _ = (args, kwargs)
        raise AssertionError("当前运行扫描缓存不应调用翻译源 strict scan")

    if hasattr(runtime_audit_module, "scan_plugin_source_files_text_strict"):
        monkeypatch.setattr(
            runtime_audit_module,
            "scan_plugin_source_files_text_strict",
            forbidden_translation_source_strict_scan,
        )
    monkeypatch.setattr(
        runtime_audit_module,
        "scan_plugin_source_runtime_files_text_strict",
        counting_scan,
    )
    second_report = await service.audit_active_runtime(game_title="テストゲーム")
    assert second_report.status == "ok"
    assert second_report.summary["active_runtime_scan_cache_hit_file_count"] == cached_file_count
    assert second_report.summary["active_runtime_scan_cache_miss_file_count"] == 0
    assert second_report.summary["active_runtime_scan_cache_stale_file_count"] == 0
    assert second_report.summary["active_runtime_scan_cache_rescan_file_count"] == 0
    assert scan_calls == []

    _ = source_path.write_text("const Messages = { title: 'カテゴリ変更' };\n", encoding="utf-8")
    third_report = await service.audit_active_runtime(game_title="テストゲーム")
    assert third_report.status == "ok"
    assert third_report.summary["active_runtime_scan_cache_hit_file_count"] == cached_file_count - 1
    assert third_report.summary["active_runtime_scan_cache_stale_file_count"] == 1
    assert third_report.summary["active_runtime_scan_cache_rescan_file_count"] == 1
    assert scan_calls == [("CacheSource.js",)]


@pytest.mark.asyncio
async def test_plugin_source_runtime_scan_cache_invalidates_contract_change(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行插件源码扫描缓存契约版本变化时必须重扫。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "ContractCacheSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "ContractCacheSource.js").write_text(
        "const Messages = { title: 'カテゴリ' };\n",
        encoding="utf-8",
    )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    first_report = await service.audit_active_runtime(game_title="テストゲーム")
    assert _json_int_for_assert(first_report.summary["active_runtime_scan_cache_rescan_file_count"], "rescan") > 0
    async with await registry.open_game("テストゲーム") as session:
        _ = await session.connection.execute(
            "UPDATE plugin_source_runtime_scan_cache SET parser_contract_version = parser_contract_version - 1"
        )
        await session.connection.commit()

    second_report = await service.audit_active_runtime(game_title="テストゲーム")

    assert _json_int_for_assert(second_report.summary["active_runtime_scan_cache_stale_file_count"], "stale") > 0
    assert _json_int_for_assert(second_report.summary["active_runtime_scan_cache_rescan_file_count"], "rescan") > 0


@pytest.mark.asyncio
async def test_audit_active_runtime_rebuilds_incomplete_literal_cache(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行源码 literal cache 缺少 native 分类字段时应重扫。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "IncompleteRuntimeCache", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source_text = "const Messages = { title: 'カテゴリ' };\n"
    _ = (plugin_source_dir / "IncompleteRuntimeCache.js").write_text(source_text, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    incomplete_literals = [
        {
            "selector": "ast:string:0:0:incomplete-cache",
            "text": "カテゴリ",
            "raw_text": "'カテゴリ'",
            "line": 1,
            "start_index": 28,
            "end_index": 34,
            "context": "assignment",
        }
    ]
    async with await registry.open_game("テストゲーム") as session:
        _ = await session.connection.execute(
            """
            INSERT INTO plugin_source_runtime_scan_cache
            (
                file_name,
                file_hash,
                rust_contract_version,
                parser_contract_version,
                audit_contract_version,
                syntax_error,
                literals_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "IncompleteRuntimeCache.js",
                build_plugin_source_file_hash(source_text),
                PLUGIN_SOURCE_RUNTIME_SCAN_RUST_CONTRACT_VERSION,
                PLUGIN_SOURCE_RUNTIME_SCAN_PARSER_CONTRACT_VERSION,
                PLUGIN_SOURCE_RUNTIME_AUDIT_CONTRACT_VERSION,
                "",
                json.dumps(incomplete_literals, ensure_ascii=False, separators=(",", ":")),
                "2026-06-07T00:00:00",
            ),
        )
        await session.commit()

    report = await service.audit_active_runtime(game_title="テストゲーム")

    assert report.status == "ok"
    assert report.summary["active_runtime_scan_cache_input_record_count"] == 0
    rescan_file_count = report.summary["active_runtime_scan_cache_rescan_file_count"]
    assert isinstance(rescan_file_count, int)
    assert rescan_file_count >= 1
    async with await registry.open_game("テストゲーム") as session:
        refreshed_records = await session.read_plugin_source_runtime_scan_cache()
    incomplete_record = next(record for record in refreshed_records if record.file_name == "IncompleteRuntimeCache.js")
    assert incomplete_record.literals[0].literal_kind == "user_visible_candidate"


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
async def test_import_placeholder_rules_uses_current_text_fact_without_full_source_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通占位符规则导入必须使用当前文本事实范围。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands.insert(1, {"code": 401, "parameters": [r"\ShakeStop this!!!"]})
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False), encoding="utf-8")

    async def forbidden_load_game_data_for_view(
        game_path: str | Path,
        *,
        view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> NoReturn:
        _ = (game_path, view, include_plugin_source_files, include_writable_copies, run_dialogue_probe_check)
        raise AssertionError("import-placeholder-rules 不应加载完整翻译源")

    class V2OnlyPlaceholderService(AgentToolkitService):
        @override
        async def _extract_active_translation_data_map(
            self,
            *,
            session: TargetGameSession,
            game_data: GameData,
            text_rules: TextRules,
            plugin_source_scan: PluginSourceScan | None = None,
        ) -> NoReturn:
            _ = (session, game_data, text_rules, plugin_source_scan)
            raise AssertionError("import-placeholder-rules 必须使用当前文本事实范围")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    monkeypatch.setattr("app.agent_toolkit.services.core.load_game_data_for_view", forbidden_load_game_data_for_view)
    service = V2OnlyPlaceholderService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    assert report.status in {"ok", "warning"}
    uncovered_count = _json_int_for_assert(report.summary["uncovered_count"], "summary.uncovered_count")
    assert uncovered_count >= 1
    coverage = ensure_json_object(report.details["coverage"], "placeholder coverage")
    coverage_summary = ensure_json_object(coverage["summary"], "placeholder coverage.summary")
    assert _json_int_for_assert(coverage_summary["candidate_count"], "coverage.summary.candidate_count") >= 1
    assert _json_int_for_assert(coverage_summary["uncovered_count"], "coverage.summary.uncovered_count") == uncovered_count
@pytest.mark.asyncio
async def test_validate_placeholder_rules_uses_warm_text_index_coverage(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """warm index 可用时，占位符规则校验复用当前索引覆盖结果。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)

    report = await service.validate_placeholder_rules(
        game_title="テストゲーム",
        custom_placeholder_rules_text="{}",
        sample_texts=[],
    )

    assert report.status in {"ok", "warning"}
    assert report.summary["rule_count"] == 0
@pytest.mark.asyncio
async def test_import_placeholder_rules_uses_warm_text_index_coverage(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """warm index 可用时，占位符规则导入复用索引完成验证和覆盖检查。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    assert report.status in {"ok", "warning"}
    assert report.summary["imported_rule_count"] == 0


@pytest.mark.asyncio
async def test_source_residual_rule_commands_use_warm_text_index_fact_lookup(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 可用时，源文残留规则命令只按规则路径读取索引事实。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        text_index_items = await session.read_text_index_items()
    target_item = next(
        item
        for item in text_index_items
        if "こんにちは" in "\n".join(item.original_lines)
    )
    async with await registry.open_game("テストゲーム") as session:
        await write_current_translation_items_for_test(session,
            [
                TranslationItem(
                    location_path=target_item.location_path,
                    item_type=target_item.item_type,
                    role=target_item.role,
                    original_lines=list(target_item.original_lines),
                    source_line_paths=list(target_item.source_line_paths),
                    translation_lines=["保存済み"],
                )
            ]
        )
    rules_text = json.dumps(
        {
            "position_rules": {
                target_item.location_path: {
                    "allowed_terms": ["保存済み"],
                    "reason": "saved_translation_term",
                }
            },
            "structural_rules": [],
        },
        ensure_ascii=False,
    )

    async def forbidden_full_translation_read(self: TargetGameSession) -> NoReturn:
        _ = self
        raise AssertionError("源文残留规则命令不应全量读取所有已保存译文")

    monkeypatch.setattr(TargetGameSession, "read_translated_items", forbidden_full_translation_read)

    validate_report = await service.validate_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    import_report = await service.import_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    assert validate_report.status == "ok"
    assert validate_report.summary["position_rule_count"] == 1
    assert import_report.status == "ok"
    assert import_report.summary["position_rule_count"] == 1
@pytest.mark.asyncio
async def test_import_structured_placeholder_rules_saves_separate_records(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化占位符规则单独保存，不混入普通正则占位符规则表。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "MINI_LABEL",
                    "pattern": r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
                        "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    validate_report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=["<Mini Label: Alraune>"],
    )
    import_report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    async with await registry.open_game("テストゲーム") as session:
        placeholder_records = await session.read_placeholder_rules()
        structured_records = await session.read_structured_placeholder_rules()

    assert validate_report.status == "ok"
    assert import_report.status in {"ok", "warning"}
    assert placeholder_records == []
    assert structured_records == [
        StructuredPlaceholderRuleRecord(
            rule_name="MINI_LABEL",
            rule_type="paired_shell",
            pattern_text=r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
            translatable_group="text",
            protected_groups={
                "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
                "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
            },
        )
    ]
@pytest.mark.asyncio
async def test_import_structured_placeholder_rules_uses_current_text_fact_without_text_index_wrapper(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """结构化占位符规则导入使用 current text facts，不走旧 text-index wrapper。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands.insert(1, {"code": 401, "parameters": ["<Mini Label: 薬草>"]})
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False), encoding="utf-8")

    async def forbidden_load_game_data_for_view(
        game_path: str | Path,
        *,
        view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> NoReturn:
        _ = (game_path, view, include_plugin_source_files, include_writable_copies, run_dialogue_probe_check)
        raise AssertionError("import-structured-placeholder-rules 不应加载完整翻译源")

    class V2OnlyStructuredPlaceholderService(AgentToolkitService):
        @override
        async def _read_active_translation_data_map_from_text_index(
            self,
            *,
            session: TargetGameSession,
            text_rules: TextRules,
        ) -> NoReturn:
            _ = (session, text_rules)
            raise AssertionError("import-structured-placeholder-rules 不应走旧 text-index wrapper")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    monkeypatch.setattr("app.agent_toolkit.services.core.load_game_data_for_view", forbidden_load_game_data_for_view)
    service = V2OnlyStructuredPlaceholderService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text='{"paired_shell_rules": []}',
        confirm_empty=True,
    )

    assert report.status in {"ok", "warning"}
    uncovered_count = _json_int_for_assert(report.summary["uncovered_count"], "summary.uncovered_count")
    assert uncovered_count >= 1
    coverage = ensure_json_object(report.details["coverage"], "structured placeholder coverage")
    coverage_summary = ensure_json_object(coverage["summary"], "structured placeholder coverage.summary")
    assert _json_int_for_assert(coverage_summary["candidate_count"], "coverage.summary.candidate_count") >= 1
    assert _json_int_for_assert(coverage_summary["uncovered_count"], "coverage.summary.uncovered_count") == uncovered_count
@pytest.mark.asyncio
async def test_import_empty_placeholder_rules_confirms_uncovered_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """空普通占位符规则确认后，未覆盖候选不再卡住流程。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    missing_report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
    )
    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )
    doctor_report = await service.doctor(game_title="テストゲーム", check_llm=False)
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=PLACEHOLDER_RULE_DOMAIN)
        coverage = build_normal_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            text_rules=text_rules,
            rule_count=0,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert missing_report.status == "error"
    assert "confirm-empty" in missing_report.errors[0].message
    assert report.status == "warning"
    assert {"placeholder_rules_empty", "placeholder_uncovered_reviewed"} <= {warning.code for warning in report.warnings}
    assert report.summary["uncovered_count"] != 0
    assert "placeholder_uncovered_reviewed" in {warning.code for warning in doctor_report.warnings}
    assert state is not None
    assert state.reviewed_empty is True
    assert state.scope_hash == coverage.scope_hash
    assert "placeholder_uncovered" not in {error.code for error in errors}
@pytest.mark.asyncio
async def test_import_empty_placeholder_rules_uses_full_candidate_hash(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """普通占位符导入确认必须用完整候选集合计算 hash，不能只用 stdout 样本。"""
    _insert_common_event_texts(
        minimal_english_game_dir,
        [fr"\ZZCustom{index}[Face{index}] Line {index}" for index in range(120)],
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_placeholder_rules(
        game_title="English Fixture Game",
        rules_text="{}",
        confirm_empty=True,
    )

    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=PLACEHOLDER_RULE_DOMAIN)
    coverage = build_normal_placeholder_coverage_result(
        translation_data_map=scope.translation_data_map,
        text_rules=text_rules,
        rule_count=0,
    )
    sampled_hash = "stale-sampled-placeholder-hash"

    assert report.status == "warning"
    assert coverage.candidate_count > 100
    assert state is not None
    assert state.scope_hash == coverage.scope_hash
    assert state.scope_hash != sampled_hash
@pytest.mark.asyncio
async def test_confirmed_empty_placeholder_risk_allows_quality_warning_and_write_back(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认空占位符风险后，正确保留协议片段的译文必须能写回。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    _ = (app_home / "setting.toml").write_text(
        example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=app_home / "setting.toml")
    placeholder_report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )
    structured_report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"paired_shell_rules": []}, ensure_ascii=False),
        confirm_empty=True,
    )
    pending_path = tmp_path / "pending-translations.json"
    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )

    setting = load_setting(app_home / "setting.toml", source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    payload = load_json_object(pending_path)
    manual_payload: dict[str, object] = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        translation_lines: list[str] = []
        for raw_line in original_lines:
            if not isinstance(raw_line, str):
                raise TypeError(f"{location_path}.original_lines 必须是字符串数组")
            translation_lines.append(
                _translated_test_line_preserving_protocol_candidates(raw_line, text_rules)
            )
        manual_entry: JsonObject = {key: value for key, value in entry.items()}
        manual_entry["translation_lines"] = [cast(JsonValue, line) for line in translation_lines]
        manual_payload[location_path] = manual_entry
    manual_path = tmp_path / "manual-translations.json"
    _ = manual_path.write_text(json.dumps(manual_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _ = await _rebuild_text_index_for_test(service)

    manual_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=manual_path,
    )
    quality_report = await service.quality_report(game_title="テストゲーム")
    handler = TranslationHandler(registry, LLMHandler())
    try:
        write_summary = await handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    assert placeholder_report.status == "warning"
    assert placeholder_report.summary["uncovered_count"] != 0
    assert structured_report.status in {"ok", "warning"}
    assert export_report.status == "ok"
    assert manual_report.status == "ok"
    assert quality_report.status == "warning", quality_report.to_json_text()
    assert {warning.code for warning in quality_report.warnings} == {"placeholder_uncovered_reviewed"}
    assert quality_report.errors == []
    assert write_summary.data_item_count > 0
@pytest.mark.asyncio
async def test_import_nonempty_placeholder_rules_confirms_remaining_uncovered_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """非空普通占位符规则仍有候选时，保存 reviewed_empty=false 的风险确认。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"NO_MATCH": "[CUSTOM_NO_MATCH_{index}]"}, ensure_ascii=False),
    )
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=PLACEHOLDER_RULE_DOMAIN)
        coverage = build_normal_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            text_rules=text_rules,
            rule_count=1,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert report.status == "warning"
    assert "placeholder_uncovered_reviewed" in {warning.code for warning in report.warnings}
    assert report.summary["imported_rule_count"] == 1
    assert report.summary["uncovered_count"] != 0
    assert state is not None
    assert state.reviewed_empty is False
    assert state.scope_hash == coverage.scope_hash
    assert "placeholder_uncovered" not in {error.code for error in errors}
@pytest.mark.asyncio
async def test_import_empty_structured_placeholder_rules_confirms_uncovered_candidates(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """空结构化占位符规则确认后，协议外壳候选不再卡住流程。"""
    _replace_first_common_event_text(minimal_english_game_dir, "<名前: Alraune>")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    missing_report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text='{"paired_shell_rules": []}',
    )
    report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text='{"paired_shell_rules": []}',
        confirm_empty=True,
    )
    doctor_report = await service.doctor(game_title="English Fixture Game", check_llm=False)
    game_data = await load_active_runtime_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN)
        coverage = build_structured_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            structured_rules=text_rules.structured_placeholder_rules,
            rule_count=0,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert missing_report.status == "error"
    assert "confirm-empty" in missing_report.errors[0].message
    assert report.status == "warning"
    assert {"structured_placeholder_rules_empty", "structured_placeholder_uncovered_reviewed"} <= {
        warning.code
        for warning in report.warnings
    }
    assert report.summary["uncovered_count"] == 1
    assert "structured_placeholder_uncovered_reviewed" in {warning.code for warning in doctor_report.warnings}
    assert state is not None
    assert state.reviewed_empty is True
    assert state.scope_hash == coverage.scope_hash
    assert "structured_placeholder_uncovered" not in {error.code for error in errors}


@pytest.mark.asyncio
async def test_import_empty_structured_placeholder_rules_respects_custom_placeholder_coverage(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化空规则确认必须复用普通 custom placeholder 覆盖事实。"""
    _replace_first_common_event_text(minimal_english_game_dir, "<Face:1>")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    placeholder_report = await service.import_placeholder_rules(
        game_title="English Fixture Game",
        rules_text=json.dumps({r"<Face:\d+>": "[CUSTOM_FACE_ID_{index}]"}, ensure_ascii=False),
    )

    structured_report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text='{"paired_shell_rules": []}',
        confirm_empty=True,
    )

    assert placeholder_report.status == "ok"
    assert structured_report.summary["uncovered_count"] == 0
    assert "structured_placeholder_uncovered_reviewed" not in {
        warning.code
        for warning in structured_report.warnings
    }


@pytest.mark.asyncio
async def test_import_empty_structured_placeholder_rules_uses_full_candidate_hash(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化占位符导入确认必须用完整候选集合计算 hash，不能只用前 100 个样本。"""
    _insert_common_event_texts(
        minimal_english_game_dir,
        [f"<Name{index}: Alice{index}>" for index in range(120)],
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text='{"paired_shell_rules": []}',
        confirm_empty=True,
    )

    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN)
    coverage = build_structured_placeholder_coverage_result(
        translation_data_map=scope.translation_data_map,
        structured_rules=text_rules.structured_placeholder_rules,
        rule_count=0,
    )
    sampled_hash = "stale-sampled-structured-placeholder-hash"

    assert report.status == "warning"
    assert coverage.candidate_count > 100
    assert state is not None
    assert state.scope_hash == coverage.scope_hash
    assert state.scope_hash != sampled_hash
@pytest.mark.asyncio
async def test_import_nonempty_structured_placeholder_rules_confirms_remaining_uncovered_candidates(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """非空结构化规则仍未覆盖候选时，保存 reviewed_empty=false 的风险确认。"""
    _replace_first_common_event_text(minimal_english_game_dir, "<名前: Alraune>")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "NEVER",
                    "pattern": r"(?P<open><Never>)(?P<text>[^<>\r\n]+)(?P<close></Never>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_NEVER_OPEN_{index}]",
                        "close": "[CUSTOM_NEVER_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text=rules_text,
    )
    game_data = await load_active_runtime_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN)
        coverage = build_structured_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            structured_rules=text_rules.structured_placeholder_rules,
            rule_count=1,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert report.status == "warning"
    assert "structured_placeholder_uncovered_reviewed" in {warning.code for warning in report.warnings}
    assert report.summary["imported_rule_count"] == 1
    assert report.summary["uncovered_count"] == 1
    assert state is not None
    assert state.reviewed_empty is False
    assert state.scope_hash == coverage.scope_hash
    assert "structured_placeholder_uncovered" not in {error.code for error in errors}
@pytest.mark.asyncio
async def test_placeholder_candidate_review_rejects_sampled_hash(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """前 100 候选 hash 不能代表当前完整候选范围。"""
    _insert_common_event_texts(
        minimal_english_game_dir,
        [fr"\ZZSample{index}[Face{index}] Line {index}" for index in range(120)],
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    game_data = await load_active_runtime_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        coverage = build_normal_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            text_rules=text_rules,
            rule_count=0,
        )
        sampled_hash = "stale-sampled-placeholder-hash"
        await session.replace_rule_review_state(
            rule_domain=PLACEHOLDER_RULE_DOMAIN,
            scope_hash=sampled_hash,
            reviewed_empty=True,
        )
        decisions = await collect_placeholder_candidate_review_decisions(
            session=session,
            scope=scope,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            stage="workflow_gate",
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    placeholder_decision = next(decision for decision in decisions if decision.rule_domain == PLACEHOLDER_RULE_DOMAIN)
    assert coverage.candidate_count > 100
    assert placeholder_decision.confirmation_status == "stale"
    assert placeholder_decision.severity == "error"
    assert placeholder_decision.code == "placeholder_uncovered"
    assert "placeholder_uncovered" in {error.code for error in errors}
@pytest.mark.asyncio
async def test_structured_placeholder_candidate_review_rejects_sampled_hash(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化占位符前 100 候选 hash 不能代表当前完整候选范围。"""
    _insert_common_event_texts(
        minimal_english_game_dir,
        [f"<Sample{index}: Alice{index}>" for index in range(120)],
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    game_data = await load_active_runtime_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        coverage = build_structured_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            structured_rules=text_rules.structured_placeholder_rules,
            rule_count=0,
        )
        sampled_hash = "stale-sampled-structured-placeholder-hash"
        await session.replace_rule_review_state(
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            scope_hash=sampled_hash,
            reviewed_empty=True,
        )
        decisions = await collect_placeholder_candidate_review_decisions(
            session=session,
            scope=scope,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            stage="workflow_gate",
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    structured_decision = next(
        decision
        for decision in decisions
        if decision.rule_domain == STRUCTURED_PLACEHOLDER_RULE_DOMAIN
    )
    assert coverage.candidate_count > 100
    assert structured_decision.confirmation_status == "stale"
    assert structured_decision.severity == "error"
    assert structured_decision.code == "structured_placeholder_uncovered"
    assert "structured_placeholder_uncovered" in {error.code for error in errors}


def test_structured_placeholder_coverage_result_uses_current_candidate_details() -> None:
    """结构化占位符覆盖结果使用当前候选明细。"""
    translation_data_map = {
        "CommonEvents.json": TranslationData(
            display_name=None,
            translation_items=[
                TranslationItem(
                    location_path="CommonEvents.json/1/list/0/parameters/0",
                    item_type="short_text",
                    original_lines=["<名前: Alraune> trailing text"],
                )
            ],
        )
    }
    structured_rule = StructuredPlaceholderRule.create(
        rule_name="INLINE_NAME",
        rule_type="paired_shell",
        pattern_text=r"(?P<open><名前:\s*)(?P<text>[^>\r\n]+)(?P<close>>)",
        translatable_group="text",
        protected_groups={
            "open": "[CUSTOM_INLINE_NAME_OPEN_{index}]",
            "close": "[CUSTOM_INLINE_NAME_CLOSE_{index}]",
        },
    )

    coverage = build_structured_placeholder_coverage_result(
        translation_data_map=translation_data_map,
        structured_rules=(structured_rule,),
        rule_count=1,
    )

    assert coverage.candidate_count == 1
    assert coverage.covered_count == 1
    assert coverage.uncovered_count == 0
    assert coverage.scope_hash
    detail = ensure_json_object(coverage.candidates[0], "structured placeholder candidate")
    assert detail["location_path"] == "CommonEvents.json/1/list/0/parameters/0"
    assert detail["candidate"] == "<名前: Alraune>"
    assert detail["covered"] is True
    assert detail["matching_rules"] == ["INLINE_NAME"]
@pytest.mark.asyncio
async def test_placeholder_candidate_review_state_mismatch_blocks_workflow(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """候选范围变化后，旧的占位符候选风险确认不能继续放行。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        await session.replace_rule_review_state(
            rule_domain=PLACEHOLDER_RULE_DOMAIN,
            scope_hash="stale-placeholder-scope",
            reviewed_empty=True,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert "placeholder_uncovered" in {error.code for error in errors}
def test_placeholder_candidate_scan_accepts_custom_span_wrapping_candidate() -> None:
    """自定义规则包住内部标准形态候选时，扫描门禁应认定已覆盖。"""
    translation_data_map = {
        "Items.json": TranslationData(
            display_name=None,
            translation_items=[
                TranslationItem(
                    location_path="Items.json/293/note/SG説明",
                    item_type="short_text",
                    original_lines=[r"\\v[104] / 5"],
                )
            ],
        )
    }
    text_rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(
                r"\\\\v\[[0-9]+\]",
                "[CUSTOM_ESCAPED_VARIABLE_{index}]",
            ),
        ),
    )

    candidates = collect_native_placeholder_candidate_details(
        translation_data_map=translation_data_map,
        text_rules=text_rules,
    )
    first_candidate = ensure_json_object(candidates[0], "placeholder_candidates[0]")

    assert count_uncovered_placeholder_candidate_details(candidates) == 0
    assert first_candidate["marker"] == r"\\v[104]"
    assert first_candidate["custom_covered"] is True


def test_normal_placeholder_coverage_result_uses_native_candidate_scan(
) -> None:
    """普通占位符覆盖结果使用当前候选明细。"""
    translation_data_map = {
        "Items.json": TranslationData(
            display_name=None,
            translation_items=[
                TranslationItem(
                    location_path="Items.json/1/description",
                    item_type="short_text",
                    original_lines=[r"\F[GuideA] 説明"],
                )
            ],
        )
    }
    text_rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(
                r"\\F\[[^\]\r\n]+\]",
                "[CUSTOM_FACE_PORTRAIT_{index}]",
            ),
        ),
    )

    coverage = build_normal_placeholder_coverage_result(
        translation_data_map=translation_data_map,
        text_rules=text_rules,
        rule_count=1,
    )

    assert coverage.candidate_count == 1
    assert coverage.covered_count == 1
    assert coverage.uncovered_count == 0
    detail = ensure_json_object(coverage.candidates[0], "placeholder candidate")
    assert detail["marker"] == r"\F[GuideA]"
    assert detail["custom_covered"] is True
    assert detail["covered"] is True


@pytest.mark.asyncio
async def test_build_placeholder_rules_groups_similar_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """规则草稿会把同类自定义控制符合并成少量通用正则。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_external_text_rules(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
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
    await _install_minimal_external_text_rules(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=output_path)

    assert report.status == "ok"
    rules = load_json_object(output_path)
    assert rules[r"\\N\d*(?![A-Za-z\[])"] == "[CUSTOM_PLUGIN_N_MARKER_{index}]"
    assert r"(?i)\\N\d*(?![A-Za-z\[])" not in rules
@pytest.mark.asyncio
async def test_placeholder_rule_draft_requires_external_rules_and_uses_active_sources(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """占位符草稿必须等外部规则完成后再基于完整文本集合生成。"""
    game_data = await load_active_runtime_game_data(minimal_game_dir)
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

    blocked_report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=before_rules_path)

    fresh_game_data = await load_active_runtime_game_data(minimal_game_dir)
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

    assert blocked_report.status == "error"
    assert {error.code for error in blocked_report.errors} >= {
        "plugin_text_missing",
        "event_command_text_missing",
        "note_tag_text_missing",
    }
    assert not before_rules_path.exists()
    assert isinstance(draft_rule_count, int)
    assert draft_rule_count >= 4
    assert any(r"\\PX" in pattern for pattern in after_rules)
    assert any(r"\\EV" in pattern for pattern in after_rules)
    assert any(r"\\NT" in pattern for pattern in after_rules)
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
async def test_validate_plugin_rules_uses_prefix_read_for_translated_count(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件规则校验只读取规则插件前缀内的已保存译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    fresh_game_data = await load_active_runtime_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(fresh_game_data.plugins_js[0]),
                    path_templates=["$['parameters']['Nested']['text']"],
                )
            ]
        )
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        await write_current_translation_items_for_test(session,
            [
                TranslationItem(
                    location_path="plugins.js/0/Nested/text",
                    item_type="short_text",
                    original_lines=["ネスト本文"],
                    translation_lines=["嵌套正文"],
                ),
            ]
        )

    report = await service.validate_plugin_rules(
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

    assert report.status == "ok"
    assert report.summary["hit_count"] == 1
    assert report.summary["translated_count"] == 1
    rule_details = ensure_json_array(coerce_json_value(report.details["rules"]), "rules")
    first_rule_detail = ensure_json_object(rule_details[0], "rules[0]")
    assert first_rule_detail["translated_count"] == 1


@pytest.mark.asyncio
async def test_validate_plugin_rules_uses_native_plugin_config_hit_details(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件规则校验报告必须消费 native hit_details。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    fresh_game_data = await load_active_runtime_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(fresh_game_data.plugins_js[0]),
                    path_templates=["$['parameters']['Nested']['text']"],
                )
            ]
        )
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        await write_current_translation_items_for_test(session,
            [
                TranslationItem(
                    location_path="plugins.js/0/Nested/text",
                    item_type="short_text",
                    original_lines=["ネスト本文"],
                    translation_lines=["嵌套正文"],
                )
            ]
        )

    def forbidden_old_record_builder(**_kwargs: object) -> list[PluginTextRuleRecord]:
        raise AssertionError("validate-plugin-rules 必须消费 Rust 插件参数规则候选输出")

    monkeypatch.setattr(
        "app.agent_toolkit.services.rule_validation.build_plugin_rule_records_from_import",
        forbidden_old_record_builder,
        raising=False,
    )

    report = await service.validate_plugin_rules(
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

    assert report.status == "ok"
    assert report.summary["hit_count"] == 1
    assert report.summary["translated_count"] == 1
    rule_details = ensure_json_array(coerce_json_value(report.details["rules"]), "rules")
    first_rule_detail = ensure_json_object(rule_details[0], "rules[0]")
    assert first_rule_detail["plugin_index"] == 0
    assert first_rule_detail["paths"] == ["$['parameters']['Nested']['text']"]
    assert first_rule_detail["hit_count"] == 1
    assert first_rule_detail["translated_count"] == 1
@pytest.mark.asyncio
async def test_validate_plugin_rules_rejects_english_protocol_value_paths(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件规则校验会把英文模式下只命中协议值的路径报告为错误。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_plugin_rules(
        game_title="English Fixture Game",
        rules_text=json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "VisiblePlugin",
                    "paths": ["$['parameters']['Enabled']"],
                }
            ],
            ensure_ascii=False,
        ),
    )

    assert report.status == "error"
    assert {error.code for error in report.errors} == {"plugin_rules_invalid"}
    assert "没有命中玩家可见可翻译文本" in report.errors[0].message
@pytest.mark.asyncio
async def test_plain_rule_validation_skips_plugin_source_file_loading(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件参数、Note 和事件指令规则校验不读取插件源码文件。"""
    load_flags: list[bool] = []

    async def counting_load_game_data_for_view(
        game_path: str | Path,
        *,
        view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        load_flags.append(include_plugin_source_files)
        if include_plugin_source_files:
            raise AssertionError("普通规则校验不应读取插件源码文件")
        return await real_load_game_data_for_view(
            game_path,
            view=view,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    monkeypatch.setattr("app.agent_toolkit.services.core.load_game_data_for_view", counting_load_game_data_for_view)
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    plugin_report = await service.validate_plugin_rules(game_title="テストゲーム", rules_text="[]")
    note_report = await service.validate_note_tag_rules(game_title="テストゲーム", rules_text="{}")
    event_report = await service.validate_event_command_rules(game_title="テストゲーム", rules_text="{}")

    assert plugin_report.summary["rule_count"] == 0
    assert note_report.summary["tag_count"] == 0
    assert event_report.summary["path_rule_count"] == 0
    assert load_flags == [False, False, False]
@pytest.mark.asyncio
async def test_mv_namebox_rule_validation_skips_plugin_source_file_loading(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MV 虚拟名字框规则校验只需要 data 事件，不读取插件源码文件。"""
    load_flags: list[bool] = []

    async def counting_load_game_data_for_view(
        game_path: str | Path,
        *,
        view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        load_flags.append(include_plugin_source_files)
        if include_plugin_source_files:
            raise AssertionError("MV 虚拟名字框规则校验不应读取插件源码文件")
        return await real_load_game_data_for_view(
            game_path,
            view=view,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    monkeypatch.setattr("app.agent_toolkit.services.core.load_game_data_for_view", counting_load_game_data_for_view)
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )

    assert report.summary["rule_count"] == 1
    assert load_flags == [False]
@pytest.mark.asyncio
async def test_validate_note_tag_rules_uses_prefix_read_for_translated_count(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签规则校验只读取规则文件前缀内的已保存译文。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:一行目>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
        )
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        await write_current_translation_items_for_test(
            session,
            [
                TranslationItem(
                    location_path="Items.json/1/note/拡張説明",
                    item_type="short_text",
                    original_lines=["一行目"],
                    translation_lines=["第一行"],
                ),
            ]
        )

    report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"Items.json": ["拡張説明"]}, ensure_ascii=False),
    )

    assert report.status == "ok"
    assert report.summary["hit_count"] == 1
    assert report.summary["translated_count"] == 1
    rule_details = ensure_json_array(coerce_json_value(report.details["rules"]), "rules")
    first_rule_detail = ensure_json_object(rule_details[0], "rules[0]")
    assert first_rule_detail["translated_count"] == 1


@pytest.mark.asyncio
async def test_validate_note_tag_rules_does_not_count_same_path_stale_fact_as_translated(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签规则校验按当前 fact_id 统计译文，不能把同路径旧正文算作已翻译。"""
    items_path = minimal_mv_game_dir / "www" / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:現在の説明>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("MVテストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
        )
    _ = await _rebuild_text_index_for_test(service, game_title="MVテストゲーム")
    async with await registry.open_game("MVテストゲーム") as session:
        scope = await read_current_text_fact_scope(session)
        facts = await read_current_text_fact_records(session, limit=None)
        current_fact = next(
            fact
            for fact in facts
            if fact.domain == "note_tag"
            and fact.location_path == "Items.json/1/note/拡張説明"
            and fact.translatable_text == "現在の説明"
        )
        stale_fact = type(current_fact)(
            fact_id=f"{current_fact.fact_id}:stale",
            schema_version=current_fact.schema_version,
            domain=current_fact.domain,
            location_path=current_fact.location_path,
            source_file=current_fact.source_file,
            source_type=current_fact.source_type,
            item_type=current_fact.item_type,
            role=current_fact.role,
            selector=current_fact.selector,
            raw_text="古い説明",
            visible_text="古い説明",
            translatable_text="古い説明",
            raw_hash=f"{current_fact.raw_hash}:stale",
            visible_hash=f"{current_fact.visible_hash}:stale",
            translatable_hash=f"{current_fact.translatable_hash}:stale",
            scope_key=current_fact.scope_key,
        )
        await session.replace_text_facts(scope=scope, facts=[*facts, stale_fact])
        stale_item = await _translation_item_from_text_fact_for_test(session, stale_fact)
        stale_item.translation_lines = ["旧说明"]
        await session.write_translation_items([stale_item])

    report = await service.validate_note_tag_rules(
        game_title="MVテストゲーム",
        rules_text=json.dumps({"Items.json": ["拡張説明"]}, ensure_ascii=False),
    )

    assert report.status == "ok"
    assert report.summary["hit_count"] == 1
    assert report.summary["translated_count"] == 0


@pytest.mark.asyncio
async def test_import_note_tag_rules_deletes_only_stale_fact_id_for_same_path(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签规则导入按 fact_id 删除同路径旧译文，保留当前译文。"""
    items_path = minimal_mv_game_dir / "www" / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:現在の説明>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("MVテストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
        )
    _ = await _rebuild_text_index_for_test(service, game_title="MVテストゲーム")
    async with await registry.open_game("MVテストゲーム") as session:
        scope = await read_current_text_fact_scope(session)
        facts = await read_current_text_fact_records(session, limit=None)
        current_fact = next(
            fact
            for fact in facts
            if fact.domain == "note_tag"
            and fact.location_path == "Items.json/1/note/拡張説明"
            and fact.translatable_text == "現在の説明"
        )
        current_fact_id = current_fact.fact_id
        stale_fact = type(current_fact)(
            fact_id=f"{current_fact.fact_id}:stale",
            schema_version=current_fact.schema_version,
            domain=current_fact.domain,
            location_path=current_fact.location_path,
            source_file=current_fact.source_file,
            source_type=current_fact.source_type,
            item_type=current_fact.item_type,
            role=current_fact.role,
            selector=current_fact.selector,
            raw_text="古い説明",
            visible_text="古い説明",
            translatable_text="古い説明",
            raw_hash=f"{current_fact.raw_hash}:stale",
            visible_hash=f"{current_fact.visible_hash}:stale",
            translatable_hash=f"{current_fact.translatable_hash}:stale",
            scope_key=current_fact.scope_key,
        )
        await session.replace_text_facts(scope=scope, facts=[*facts, stale_fact])
        current_item = await _translation_item_from_text_fact_for_test(session, current_fact)
        current_item.translation_lines = ["当前说明"]
        stale_item = await _translation_item_from_text_fact_for_test(session, stale_fact)
        stale_item.translation_lines = ["旧说明"]
        await session.write_translation_items([current_item, stale_item])

    report = await service.import_note_tag_rules(
        game_title="MVテストゲーム",
        rules_text=json.dumps({"Items.json": ["拡張説明"]}, ensure_ascii=False),
    )

    async with await registry.open_game("MVテストゲーム") as session:
        remaining_items = await session.read_translated_items()

    assert report.summary["deleted_translation_items"] == 1
    assert {item.fact_id for item in remaining_items} == {current_fact_id}


@pytest.mark.asyncio
async def test_import_note_tag_rules_expands_map_file_pattern_for_stale_fact_cleanup(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """旧 Note 规则使用 Map*.json 时，也要读取具体地图路径并按 fact_id 清理 stale 译文。"""
    map001_path = minimal_game_dir / "data" / "Map001.json"
    raw_map001 = cast(object, json.loads(map001_path.read_text(encoding="utf-8")))
    map001 = ensure_json_object(coerce_json_value(raw_map001), "Map001.json")
    map001_events = ensure_json_array(map001["events"], "Map001.json.events")
    map001_event = ensure_json_object(map001_events[2], "Map001.json.events[2]")
    map001_event["note"] = "<namePop:導き手>"
    _ = map001_path.write_text(json.dumps(map001, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Map*.json", tag_names=["namePop"])]
        )
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        scope = await read_current_text_fact_scope(session)
        facts = await read_current_text_fact_records(session, limit=None)
        current_fact = next(
            fact
            for fact in facts
            if fact.domain == "note_tag"
            and fact.location_path.startswith("Map001.json/")
            and fact.location_path.endswith("/note/namePop")
            and fact.translatable_text == "導き手"
        )
        current_fact_id = current_fact.fact_id
        stale_fact = type(current_fact)(
            fact_id=f"{current_fact.fact_id}:stale",
            schema_version=current_fact.schema_version,
            domain=current_fact.domain,
            location_path=current_fact.location_path,
            source_file=current_fact.source_file,
            source_type=current_fact.source_type,
            item_type=current_fact.item_type,
            role=current_fact.role,
            selector=current_fact.selector,
            raw_text="古い導き手",
            visible_text="古い導き手",
            translatable_text="古い導き手",
            raw_hash=f"{current_fact.raw_hash}:stale",
            visible_hash=f"{current_fact.visible_hash}:stale",
            translatable_hash=f"{current_fact.translatable_hash}:stale",
            scope_key=current_fact.scope_key,
        )
        await session.replace_text_facts(scope=scope, facts=[*facts, stale_fact])
        current_item = await _translation_item_from_text_fact_for_test(session, current_fact)
        current_item.translation_lines = ["向导"]
        stale_item = await _translation_item_from_text_fact_for_test(session, stale_fact)
        stale_item.translation_lines = ["旧向导"]
        await session.write_translation_items([current_item, stale_item])

    report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"Map*.json": ["namePop"]}, ensure_ascii=False),
    )

    async with await registry.open_game("テストゲーム") as session:
        remaining_items = await session.read_translated_items()

    assert report.summary["deleted_translation_items"] == 1
    assert {item.fact_id for item in remaining_items} == {current_fact_id}


@pytest.mark.asyncio
async def test_import_plugin_source_rules_deletes_only_stale_fact_id_for_same_path(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码规则导入按 fact_id 删除同路径旧译文，不能按 path 删除。"""
    source_path = minimal_mv_game_dir / "www" / "js" / "plugins" / "MvPlugin.js"
    source_text = "Window_Base.prototype.drawText('現在のプラグイン本文', 0, 0, 320);\n"
    _ = source_path.write_text(source_text, encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    game_data = await load_active_runtime_game_data(
        minimal_mv_game_dir,
        include_plugin_source_files=True,
        run_dialogue_probe_check=False,
    )
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=get_default_text_rules())
    candidate = next(candidate for candidate in scan.candidates if candidate.file_name == "MvPlugin.js")
    rules_text = json.dumps(
        [
            {
                "file": "MvPlugin.js",
                "selectors": [candidate.selector],
                "excluded_selectors": [],
            }
        ],
        ensure_ascii=False,
    )
    async with await registry.open_game("MVテストゲーム") as session:
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="MvPlugin.js",
                    file_hash=build_plugin_source_file_hash(source_text),
                    selectors=[candidate.selector],
                    excluded_selectors=[],
                )
            ]
        )
    _ = await _rebuild_text_index_for_test(service, game_title="MVテストゲーム")
    async with await registry.open_game("MVテストゲーム") as session:
        scope = await read_current_text_fact_scope(session)
        facts = await read_current_text_fact_records(session, limit=None)
        current_fact = next(
            fact
            for fact in facts
            if fact.domain == "plugin_source"
            and fact.location_path == f"js/plugins/MvPlugin.js/{candidate.selector}"
            and fact.translatable_text == "現在のプラグイン本文"
        )
        current_fact_id = current_fact.fact_id
        stale_fact = type(current_fact)(
            fact_id=f"{current_fact.fact_id}:stale",
            schema_version=current_fact.schema_version,
            domain=current_fact.domain,
            location_path=current_fact.location_path,
            source_file=current_fact.source_file,
            source_type=current_fact.source_type,
            item_type=current_fact.item_type,
            role=current_fact.role,
            selector=current_fact.selector,
            raw_text="古いプラグイン本文",
            visible_text="古いプラグイン本文",
            translatable_text="古いプラグイン本文",
            raw_hash=f"{current_fact.raw_hash}:stale",
            visible_hash=f"{current_fact.visible_hash}:stale",
            translatable_hash=f"{current_fact.translatable_hash}:stale",
            scope_key=current_fact.scope_key,
        )
        await session.replace_text_facts(scope=scope, facts=[*facts, stale_fact])
        current_item = await _translation_item_from_text_fact_for_test(session, current_fact)
        current_item.translation_lines = ["当前插件正文"]
        stale_item = await _translation_item_from_text_fact_for_test(session, stale_fact)
        stale_item.translation_lines = ["旧插件正文"]
        await session.write_translation_items([current_item, stale_item])

    async def forbidden_path_delete(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("规则导入不得按 location_path 删除译文")

    monkeypatch.setattr(TargetGameSession, "delete_translation_items_by_paths", forbidden_path_delete)

    report = await service.import_plugin_source_rules(
        game_title="MVテストゲーム",
        rules_text=rules_text,
    )

    async with await registry.open_game("MVテストゲーム") as session:
        remaining_items = await session.read_translated_items()

    assert report.summary["deleted_translation_items"] == 1
    assert {item.fact_id for item in remaining_items} == {current_fact_id}


@pytest.mark.asyncio
async def test_rule_fact_resolver_does_not_match_same_path_when_text_differs(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """规则命中解析必须匹配正文；同 path 唯一 fact 也不能冒充命中。"""
    items_path = minimal_mv_game_dir / "www" / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:現在の説明>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("MVテストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
        )
    _ = await _rebuild_text_index_for_test(service, game_title="MVテストゲーム")

    async with await registry.open_game("MVテストゲーム") as session:
        hits = await resolve_current_rule_fact_hits(
            session,
            [
                RuleFactProbe(
                    domain="note_tag",
                    location_path="Items.json/1/note/拡張説明",
                    translatable_text="古い説明",
                )
            ],
        )

    assert hits == []


@pytest.mark.asyncio
async def test_validate_note_tag_rules_uses_native_candidate_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签规则校验必须用 native 候选摘要完成前置命中检查。"""

    def forbidden_python_record_builder(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("validate-note-tag-rules 不应调用 Python build_note_tag_rule_records_from_import")

    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = f"<拡張説明:{json.dumps('薬草の詳細', ensure_ascii=False)}>\n<upgrade:1,2,3>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "app.agent_toolkit.services.rule_validation.build_note_tag_rule_records_from_import",
        forbidden_python_record_builder,
        raising=False,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"Items.json": ["拡張説明"]}, ensure_ascii=False),
    )

    assert report.status == "ok"
    assert report.summary["file_count"] == 1
    assert report.summary["tag_count"] == 1
    assert report.summary["hit_count"] == 1
    rule_details = ensure_json_array(coerce_json_value(report.details["rules"]), "rules")
    first_rule_detail = ensure_json_object(rule_details[0], "rules[0]")
    assert first_rule_detail["file_name"] == "Items.json"
    assert first_rule_detail["tag_names"] == ["拡張説明"]


@pytest.mark.asyncio
async def test_validate_note_tag_rules_keeps_precise_map_file_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """精确地图规则不能被其它地图的 native 聚合候选误放行。"""
    map001_path = minimal_game_dir / "data" / "Map001.json"
    raw_map001 = cast(object, json.loads(map001_path.read_text(encoding="utf-8")))
    map001 = ensure_json_object(coerce_json_value(raw_map001), "Map001.json")
    map001_events = ensure_json_array(map001["events"], "Map001.json.events")
    map001_event = ensure_json_object(map001_events[2], "Map001.json.events[2]")
    map001_event["note"] = "<namePop:123>"
    _ = map001_path.write_text(json.dumps(map001, ensure_ascii=False, indent=2), encoding="utf-8")

    map002_path = minimal_game_dir / "data" / "Map002.json"
    raw_map002 = cast(object, json.loads(map002_path.read_text(encoding="utf-8")))
    map002 = ensure_json_object(coerce_json_value(raw_map002), "Map002.json")
    map002_events = ensure_json_array(map002["events"], "Map002.json.events")
    map002_event = ensure_json_object(map002_events[1], "Map002.json.events[1]")
    map002_event["note"] = "<namePop:導き手>"
    _ = map002_path.write_text(json.dumps(map002, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"Map001.json": ["namePop"]}, ensure_ascii=False),
    )

    assert report.status == "error"
    assert report.summary["file_count"] == 0
    assert any(
        issue.code == "note_tag_rules_invalid"
        and "没有命中玩家可见可翻译文本: Map001.json/namePop" in issue.message
        for issue in report.errors
    )


@pytest.mark.asyncio
async def test_import_note_tag_rules_uses_native_candidate_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签规则导入必须用 native 候选摘要完成导入前命中检查。"""

    def forbidden_python_record_builder(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("import-note-tag-rules 不应调用 Python build_note_tag_rule_records_from_import")

    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = f"<拡張説明:{json.dumps('薬草の詳細', ensure_ascii=False)}>\n<upgrade:1,2,3>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "app.agent_toolkit.services.rule_validation.build_note_tag_rule_records_from_import",
        forbidden_python_record_builder,
        raising=False,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"Items.json": ["拡張説明"]}, ensure_ascii=False),
    )

    async with await registry.open_game("テストゲーム") as session:
        rules = await session.read_note_tag_text_rules()

    assert report.status == "ok"
    assert report.summary["file_count"] == 1
    assert report.summary["tag_count"] == 1
    assert rules == [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
@pytest.mark.asyncio
async def test_import_empty_note_tag_rules_allows_confirmed_empty_with_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签候选经审查没有玩家可见文本时，可以显式保存空结果。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<PrivateProtocol:内部コード>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    missing_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text="{}",
    )
    confirmed_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    game_data = await load_active_runtime_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        state = await session.read_rule_review_state(rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN)

    assert missing_report.status == "error"
    assert "confirm-empty" in missing_report.errors[0].message
    assert confirmed_report.status == "warning"
    assert {warning.code for warning in confirmed_report.warnings} == {"note_tag_rules_empty"}
    assert state is not None
    assert state.scope_hash == note_tag_rule_scope_hash_for_text_rules(
        game_data=game_data,
        text_rules=text_rules,
    )


@pytest.mark.asyncio
async def test_note_tag_scope_hash_and_count_use_native_candidate_scan(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签空规则 hash/count 只消费 native 事实，不再触发 Python 候选扫描。"""
    from app.application import flow_gate

    native_candidates: JsonArray = [
        {
            "file_name": "Items.json",
            "tag_name": "拡張説明",
            "hit_count": 2,
            "value_hit_count": 2,
            "translatable_hit_count": 2,
            "matched_file_count": 1,
            "sample_locations": ["Items.json/1/note/拡張説明"],
            "sample_values": ["薬草の詳細"],
        },
        {
            "file_name": "Items.json",
            "tag_name": "PrivateProtocol",
            "hit_count": 1,
            "value_hit_count": 1,
            "translatable_hit_count": 0,
            "matched_file_count": 1,
            "sample_locations": ["Items.json/1/note/PrivateProtocol"],
            "sample_values": [],
        },
    ]

    def forbidden_python_note_tag_candidates(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("Note 标签 scope hash/count 不应调用 Python collect_note_tag_candidates")

    def fake_native_note_tag_candidates(*args: object, **kwargs: object) -> JsonArray:
        _ = (args, kwargs)
        return native_candidates

    def fake_native_note_tag_rule_validation(*args: object, **kwargs: object) -> JsonObject:
        _ = (args, kwargs)
        return {
            "status": "pass",
            "scope_hash": "native-note-scope-hash",
            "candidate_count": 1,
            "covered_count": 0,
            "translatable_hit_count": 0,
            "errors": [],
        }

    monkeypatch.setattr(
        flow_gate,
        "collect_note_tag_candidates",
        forbidden_python_note_tag_candidates,
        raising=False,
    )
    monkeypatch.setattr(
        flow_gate,
        "collect_native_note_tag_candidate_details",
        fake_native_note_tag_candidates,
        raising=False,
    )
    monkeypatch.setattr(
        flow_gate,
        "collect_native_note_tag_rule_validation",
        fake_native_note_tag_rule_validation,
        raising=False,
    )

    game_data = await load_active_runtime_game_data(minimal_game_dir)
    text_rules = get_default_text_rules()

    assert count_note_tag_rule_candidates(game_data=game_data, text_rules=text_rules) == 2
    assert note_tag_rule_scope_hash_for_text_rules(
        game_data=game_data,
        text_rules=text_rules,
    ) == "native-note-scope-hash"


@pytest.mark.asyncio
async def test_native_note_tag_candidates_match_python_scope_hash_input(
    minimal_game_dir: Path,
) -> None:
    """native Note 标签候选摘要必须保持 Python scope hash 输入等价。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:薬草の詳細>\n<PrivateProtocol:内部コード>\n<upgrade:1,2,3>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    game_data = await load_active_runtime_game_data(minimal_game_dir)
    text_rules = get_default_text_rules()
    native_candidates = collect_native_note_tag_candidate_details(game_data=game_data, text_rules=text_rules)

    assert native_candidates
    assert note_tag_rule_scope_hash_for_text_rules(
        game_data=game_data,
        text_rules=text_rules,
    )
@pytest.mark.asyncio
async def test_import_note_tag_rules_replaces_stale_existing_rule(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧 Note 标签规则过期时，仍然可以导入新规则并清理旧译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    missing_tag_path = "Items.json/1/note/MissingTag"
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["MissingTag"])]
        )
        await insert_invalid_fact_translation_row_for_test(
            session,
            fact_id="invalid-current-note-tag:missing-tag",
            location_path=missing_tag_path,
            item_type="short_text",
            role=None,
            original_lines=["古いタグ"],
            source_line_paths=[missing_tag_path],
            translation_lines=["待清理标签"],
        )

    async def forbidden_full_translation_read(_self: TargetGameSession) -> list[TranslationItem]:
        raise AssertionError("Note 标签规则导入不能全量读取已保存译文")

    monkeypatch.setattr(TargetGameSession, "read_translated_items", forbidden_full_translation_read)

    report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    async with await registry.open_game("テストゲーム") as session:
        rules = await session.read_note_tag_text_rules()
        paths = {
            item.location_path
            for item in await session.read_translated_items_by_prefixes(["Items.json/"])
        }

    assert report.status == "warning"
    assert report.summary["deleted_translation_items"] == 1
    assert rules == []
    assert missing_tag_path not in paths


@pytest.mark.asyncio
async def test_public_rule_validation_and_import_use_native_candidate_paths(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码和 Note 标签公共规则命令使用当前 native 候选路径。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins_json_text = plugins_text.removeprefix("var $plugins = ").rstrip(";\r\n ")
    plugins = ensure_json_array(coerce_json_value(cast(object, json.loads(plugins_json_text))), "plugins")
    plugins.append({"name": "RuleNativeGuard", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "RuleNativeGuard.js").write_text(
        "Window_Base.prototype.drawText('ガード対象本文', 0, 0, 320);\n",
        encoding="utf-8",
    )
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:薬草の詳細>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        game_data = await load_active_runtime_game_data(
            minimal_game_dir,
            include_plugin_source_files=True,
            include_writable_copies=False,
            run_dialogue_probe_check=False,
        )
        scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    candidate = next(candidate for candidate in scan.candidates if candidate.file_name == "RuleNativeGuard.js")
    plugin_rules_text = json.dumps(
        [
            {
                "file": "RuleNativeGuard.js",
                "selectors": [candidate.selector],
                "excluded_selectors": [
                    other.selector
                    for other in scan.candidates
                    if other.active
                    and other.file_name == "RuleNativeGuard.js"
                    and other.selector != candidate.selector
                ],
            }
        ],
        ensure_ascii=False,
    )
    note_rules_text = json.dumps({"Items.json": ["拡張説明"]}, ensure_ascii=False)

    plugin_ast_map_report = await service.export_plugin_source_ast_map(
        game_title="テストゲーム",
        output_path=tmp_path / "plugin-source-ast-map.json",
    )
    plugin_validate_report = await service.validate_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=plugin_rules_text,
    )
    plugin_import_report = await service.import_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=plugin_rules_text,
    )
    note_validate_report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=note_rules_text,
    )
    note_import_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text=note_rules_text,
    )

    assert plugin_ast_map_report.status == "ok"
    assert plugin_validate_report.status == "ok"
    assert plugin_validate_report.summary["hit_count"] == 1
    assert plugin_import_report.status == "ok"
    assert plugin_import_report.summary["selector_count"] == 1
    assert note_validate_report.status == "ok"
    assert note_validate_report.summary["hit_count"] == 1
    assert note_import_report.status == "ok"
    assert note_import_report.summary["tag_count"] == 1


@pytest.mark.asyncio
async def test_plugin_source_excluded_only_rule_validates_current_selector_facts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """只排除 selector 的插件源码规则也必须按当前 Rust selector facts 通过完整生命周期。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins_json_text = plugins_text.removeprefix("var $plugins = ").rstrip(";\r\n ")
    plugins = ensure_json_array(coerce_json_value(cast(object, json.loads(plugins_json_text))), "plugins")
    plugins.append({"name": "ExcludedOnlySource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "ExcludedOnlySource.js").write_text(
        "Window_Base.prototype.drawText('除外だけの本文', 0, 0, 320);\n",
        encoding="utf-8",
    )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    game_data = await load_active_runtime_game_data(
        minimal_game_dir,
        include_plugin_source_files=True,
        include_writable_copies=False,
        run_dialogue_probe_check=False,
    )
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=get_default_text_rules())
    selector = next(
        candidate.selector
        for candidate in scan.candidates
        if candidate.file_name == "ExcludedOnlySource.js"
    )
    import_payload = json.dumps(
        [
            {
                "file": "ExcludedOnlySource.js",
                "selectors": [],
                "excluded_selectors": [selector],
            }
        ],
        ensure_ascii=False,
    )

    import_report = await service.import_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=import_payload,
    )
    _ = await _rebuild_text_index_for_test(service)
    quality_report = await service.quality_report(game_title="テストゲーム")
    workflow_gate = ensure_json_object(quality_report.details["workflow_gate"], "workflow_gate")
    source_branches = ensure_json_object(workflow_gate["source_branches"], "workflow_gate.source_branches")
    plugin_source_gate = ensure_json_object(
        source_branches["plugin_source_text"],
        "workflow_gate.source_branches.plugin_source_text",
    )

    assert import_report.status == "ok"
    assert workflow_gate["source"] == "rust_text_index_gate_facts"
    assert plugin_source_gate["status"] == "pass"


@pytest.mark.asyncio
async def test_plugin_source_import_cold_rebuild_quality_and_write_back_share_rust_facts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码规则导入、冷重建、质量报告和写回共享 Rust gate facts。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins_json_text = plugins_text.removeprefix("var $plugins = ").rstrip(";\r\n ")
    plugins = ensure_json_array(coerce_json_value(cast(object, json.loads(plugins_json_text))), "plugins")
    plugins.append({"name": "LifecycleSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "LifecycleSource.js").write_text(
        "Window_Base.prototype.drawText('ライフサイクル本文', 0, 0, 320);\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    game_data = await load_active_runtime_game_data(
        minimal_game_dir,
        include_plugin_source_files=True,
        include_writable_copies=False,
        run_dialogue_probe_check=False,
    )
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=get_default_text_rules())
    selector = next(
        candidate.selector
        for candidate in scan.candidates
        if candidate.file_name == "LifecycleSource.js"
    )
    import_report = await service.import_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "LifecycleSource.js",
                    "selectors": [selector],
                    "excluded_selectors": [],
                }
            ],
            ensure_ascii=False,
        ),
    )
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        translated_items = await make_writable_current_translation_items_for_test(
            session,
            text_rules=text_rules,
        )
        for translated_item in translated_items:
            translated_item.translation_lines = [
                _translated_test_line_preserving_protocol_candidates(line, text_rules)
                for line in translated_item.original_lines
            ]
        await write_current_translation_items_for_test(session, translated_items)
        metadata = await session.read_text_index_metadata()
        assert metadata is not None
        stored_plugin_source_gate = ensure_json_object(
            metadata.workflow_gate_facts["plugin_source_text"],
            "metadata.workflow_gate_facts.plugin_source_text",
        )
    quality_report = await service.quality_report(game_title="テストゲーム")
    handler = TranslationHandler(registry, LLMHandler())
    try:
        write_summary = await handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()
    async with await registry.open_game("テストゲーム") as session:
        metadata_after_write = await session.read_text_index_metadata()
        assert metadata_after_write is not None
        stored_plugin_source_gate_after_write = ensure_json_object(
            metadata_after_write.workflow_gate_facts["plugin_source_text"],
            "metadata_after_write.workflow_gate_facts.plugin_source_text",
        )
    workflow_gate = ensure_json_object(quality_report.details["workflow_gate"], "workflow_gate")
    quality_plugin_source_gate = _workflow_gate_source_branch(quality_report, "plugin_source_text")

    assert import_report.status == "ok"
    assert workflow_gate["source"] == "rust_text_index_gate_facts"
    assert quality_plugin_source_gate["status"] == "pass"
    assert quality_plugin_source_gate["scope_hash"] == stored_plugin_source_gate["scope_hash"]
    assert stored_plugin_source_gate_after_write["scope_hash"] == stored_plugin_source_gate["scope_hash"]
    assert write_summary.data_item_count > 0


@pytest.mark.asyncio
async def test_note_tag_import_cold_rebuild_and_write_back_gate_use_rust_validation(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签规则导入后，冷重建和写回前检查继续消费 Rust gate facts。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:薬草の詳細>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    import_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"Items.json": ["拡張説明"]}, ensure_ascii=False),
    )
    pending_path = tmp_path / "pending-translations.json"
    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    payload = load_json_object(pending_path)
    manual_payload: dict[str, object] = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        translation_lines: list[str] = []
        for raw_line in original_lines:
            if not isinstance(raw_line, str):
                raise TypeError(f"{location_path}.original_lines 必须是字符串数组")
            translation_lines.append(
                _translated_test_line_preserving_protocol_candidates(raw_line, text_rules)
            )
        manual_entry: JsonObject = {key: value for key, value in entry.items()}
        manual_entry["translation_lines"] = [cast(JsonValue, line) for line in translation_lines]
        manual_payload[location_path] = manual_entry
    manual_path = tmp_path / "manual-translations.json"
    _ = manual_path.write_text(json.dumps(manual_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _ = await _rebuild_text_index_for_test(service)
    manual_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=manual_path,
    )
    quality_report = await service.quality_report(game_title="テストゲーム")
    workflow_gate = ensure_json_object(quality_report.details["workflow_gate"], "workflow_gate")
    handler = TranslationHandler(registry, LLMHandler())
    try:
        write_summary = await handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    assert import_report.status == "ok"
    assert export_report.status == "ok"
    assert manual_report.status == "ok"
    assert workflow_gate["source"] == "rust_text_index_gate_facts"
    assert write_summary.data_item_count > 0


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
    assert quality_report.summary["text_index_status"] == "cold_rebuilt"
    rebuild_summary = ensure_json_object(quality_report.summary["text_index_rebuild_summary"], "rebuild_summary")
    assert rebuild_summary["index_status"] == "rebuilt"
    assert "stale_plugin_rules" in error_codes
    assert export_report.status == "error"
    assert {error.code for error in export_report.errors} == {"stale_plugin_rules"}
    assert not pending_path.exists()
    assert workspace_report.status in {"ok", "warning"}
    assert workspace_report.summary["stale_plugin_rule_count"] == 1
    assert (tmp_path / "workspace" / "manifest.json").exists()
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
async def test_scan_placeholder_candidates_reads_current_text_fact_in_warm_index(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通占位符候选扫描命中 warm index 时也必须读取 current text facts。"""
    common_events_path = minimal_english_game_dir / "data" / "CommonEvents.json"
    raw_value = coerce_json_value(cast(object, json.loads(common_events_path.read_text(encoding="utf-8"))))
    common_events = ensure_json_array(raw_value, "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands.insert(1, {"code": 401, "parameters": [r"\ShakeStop this!!!"]})
    _ = common_events_path.write_text(json.dumps(raw_value, ensure_ascii=False), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await service.rebuild_text_index(game_title="English Fixture Game")

    def forbidden_text_index_adapter(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("scan-placeholder-candidates 不应把 text_index_items 转回正文范围")

    monkeypatch.setattr(
        "app.agent_toolkit.services.placeholder_rules.text_index_items_to_translation_data_map",
        forbidden_text_index_adapter,
        raising=False,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.text_index_items_to_translation_data_map",
        forbidden_text_index_adapter,
        raising=False,
    )

    report = await service.scan_placeholder_candidates(
        game_title="English Fixture Game",
        custom_placeholder_rules_text="{}",
    )

    assert report.status == "warning"
    assert _json_int_for_assert(report.summary["candidate_count"], "summary.candidate_count") >= 1
    assert _json_int_for_assert(report.summary["uncovered_count"], "summary.uncovered_count") >= 1


@pytest.mark.asyncio
async def test_scan_structured_placeholder_candidates_reads_current_text_fact_and_preserves_coverage(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """结构化占位符覆盖扫描使用 current text facts，并保留 standard/custom/structured 覆盖分类。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands.insert(1, {"code": 401, "parameters": [r"D_TEXT \c[17]決定ボタン 48"]})
    commands.insert(2, {"code": 401, "parameters": ["<Mini Label: 薬草>"]})
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await service.rebuild_text_index(game_title="テストゲーム")

    def forbidden_text_index_adapter(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("scan-structured-placeholder-candidates 不应把 text_index_items 转回正文范围")

    monkeypatch.setattr(
        "app.agent_toolkit.services.placeholder_rules.text_index_items_to_translation_data_map",
        forbidden_text_index_adapter,
        raising=False,
    )
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "D_TEXT_LABEL",
                    "pattern": r"(?P<open>^D_TEXT\s+)(?P<text>.*?)(?P<close>\s+48$)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_D_TEXT_OPEN_{index}]",
                        "close": "[CUSTOM_D_TEXT_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    report = await service.scan_structured_placeholder_candidates(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    candidate_bucket = ensure_json_object(report.details["candidates"], "structured coverage candidates")
    candidates = ensure_json_array(candidate_bucket["items"], "structured coverage candidate items")
    covered_by_values: set[str] = set()
    for candidate in candidates:
        covered_by = ensure_json_object(candidate, "structured coverage candidate")["covered_by"]
        if not isinstance(covered_by, str):
            raise AssertionError("structured coverage candidate.covered_by 必须是字符串")
        covered_by_values.add(covered_by)
    assert report.status in {"ok", "warning"}
    assert covered_by_values
    assert covered_by_values <= {"standard_placeholder", "custom_placeholder", "structured_placeholder", "none"}
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
    """事件指令规则报告用 native 明细按规则组统计命中数量。"""
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
async def test_validate_event_command_rules_uses_precise_hit_paths_for_translated_count(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令规则校验用 native 精确命中路径统计已保存译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
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
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        await write_current_translation_items_for_test(session,
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/4/parameters/3/message",
                    item_type="short_text",
                    original_lines=["プラグイン台詞"],
                    translation_lines=["事件指令译文"],
                ),
            ]
        )

    async def forbidden_prefix_read(
        _self: TargetGameSession,
        _prefixes: Sequence[str],
    ) -> list[TranslationItem]:
        raise AssertionError("事件指令规则校验不能逐前缀读取已保存译文")

    monkeypatch.setattr(
        TargetGameSession,
        "read_translated_items_by_prefixes",
        forbidden_prefix_read,
    )

    report = await service.validate_event_command_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            {
                "357": [
                    {
                        "match": {"0": "TestPlugin", "1": "Show"},
                        "paths": ["$['parameters'][3]['message']"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    assert report.status == "ok"
    assert report.summary["hit_count"] == 1
    assert report.summary["translated_count"] == 1
    rule_details = ensure_json_array(report.details["rules"], "rules")
    first_rule_detail = ensure_json_object(coerce_json_value(rule_details[0]), "rules[0]")
    assert first_rule_detail["translated_count"] == 1
@pytest.mark.asyncio
async def test_structured_placeholder_rule_with_standard_control_passes_validation_and_quality(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """临时游戏副本中结构化壳内的内置控制符应被项目检查放行。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands.insert(
        2,
        {
            "code": 401,
            "parameters": [r"D_TEXT \c[17]決定ボタンを連打しろ！ 48"],
        },
    )
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "D_TEXT_LABEL",
                    "pattern": r"(?P<open>^D_TEXT\s+)(?P<text>.*?)(?P<close>\s+48$)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_D_TEXT_OPEN_{index}]",
                        "close": "[CUSTOM_D_TEXT_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    validate_report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=[],
    )
    import_report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        facts = await read_current_text_fact_records(session, limit=None)
        target_fact = next(
            fact
            for fact in facts
            if "決定ボタンを連打しろ" in fact.translatable_text
        )
        target_item = await _translation_item_from_text_fact_for_test(session, target_fact)
        target_item.translation_lines = [r"D_TEXT \c[17]狂按决定键！ 48"]
        await write_current_translation_items_for_test(session,
            [
                target_item
            ]
        )
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert validate_report.errors == []
    assert import_report.errors == []
    assert quality_report.summary["placeholder_risk_count"] == 0
    assert quality_report.summary["source_residual_count"] == 0
