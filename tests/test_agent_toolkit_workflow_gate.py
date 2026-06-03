"""Agent Workflow Gate 业务契约测试。"""

from __future__ import annotations

from tests.agent_toolkit_contract_fixtures import *

@pytest.mark.asyncio
async def test_mv_workflow_gate_requires_namebox_rules_or_confirmed_empty(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 翻译流程在虚拟名字框规则未导入也未确认空规则时阻断。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("MVテストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        game_data = await load_game_data(minimal_mv_game_dir)
        session.set_game_data(game_data)
        text_rules = TextRules.from_setting(setting.text_rules)
        before_errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
        )
    empty_rejected_report = await service.import_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text='{"rules":[]}',
    )
    empty_import_report = await service.import_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text='{"rules":[]}',
        confirm_empty=True,
    )
    async with await registry.open_game("MVテストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        game_data = await load_game_data(minimal_mv_game_dir)
        session.set_game_data(game_data)
        text_rules = TextRules.from_setting(setting.text_rules)
        after_errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
        )
        state = await session.read_rule_review_state(rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN)

    assert "mv_virtual_namebox_missing" in {error.code for error in before_errors}
    assert empty_rejected_report.status == "error"
    assert empty_import_report.status == "warning"
    assert "mv_virtual_namebox_missing" not in {error.code for error in after_errors}
    assert state is not None
    assert state.scope_hash == mv_virtual_namebox_rule_scope_hash(
        mv_virtual_namebox_candidate_details(game_data)
    )
@pytest.mark.asyncio
async def test_workflow_gate_blocks_external_rule_hits_outside_writable_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """规则命中文本没有进入可写文本范围时，翻译前置硬闸必须报错。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    game_data = await load_game_data(minimal_game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    scope = TextScopeResult(
        translation_data_map={},
        entries=[
            TextScopeEntry(
                location_path="plugins.js/0/Message",
                source_type="plugin_parameter",
                rule_source="插件参数规则",
                item_type="short_text",
                original_lines=["これは翻訳対象です"],
                role=None,
                enters_translation=False,
                can_save_translation=False,
                can_write_back=False,
                translated=False,
                cannot_process_reason="规则命中项没有进入统一文本清单",
            )
        ],
    )

    async with await registry.open_game("テストゲーム") as session:
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
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert "rule_hits_unwritable" in {error.code for error in errors}
@pytest.mark.asyncio
async def test_quality_report_text_index_keeps_external_rule_workflow_gate(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """默认质量报告走文本索引时，仍要报告外部规则未确认的流程硬闸。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.quality_report(game_title="テストゲーム")

    error_codes = {error.code for error in report.errors}
    assert {
        "plugin_text_missing",
        "event_command_text_missing",
        "note_tag_text_missing",
    } <= error_codes
    assert report.summary["text_index_status"] == "cold_rebuilt"
@pytest.mark.asyncio
async def test_translate_max_items_text_index_keeps_external_rule_workflow_gate(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """小批翻译走文本索引时，外部规则未确认仍必须阻止进入模型批次。"""
    _ = app_home_with_example_setting

    async def forbidden_batches(*args: object, **kwargs: object) -> NoReturn:
        """缺少外部规则时不能进入模型批次。"""
        _ = (args, kwargs)
        raise AssertionError("外部规则未确认时 translate --max-items 不能进入模型批次")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )
    monkeypatch.setattr(
        TranslationHandler,
        "_run_prepared_translation_batches",
        forbidden_batches,
    )
    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=3),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    assert summary.text_index_status == "rebuild_failed"
    assert summary.blocked_reason is not None
    assert "插件规则" in summary.blocked_reason
    assert "事件指令规则" in summary.blocked_reason
    assert "Note 标签规则" in summary.blocked_reason
@pytest.mark.asyncio
async def test_translate_max_items_uses_text_index_after_full_workflow_gate(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """translate --max-items 先通过完整 workflow gate，再按 SQL 限制 pending。"""
    _ = app_home_with_example_setting

    captured: dict[str, int] = {}

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        captured["batch_count"] = len(batches)
        captured["item_count"] = sum(len(batch.items) for batch in batches)
        return TranslationRunState(
            total_batch_count=captured["batch_count"],
            total_item_count=captured["item_count"],
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", run_batches_with_prepared_state)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=3),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    assert summary.total_extracted_items == rebuild_report.summary["indexed_count"]
    assert summary.total_pending_count == rebuild_report.summary["indexed_count"]
    assert summary.text_index_status == "used"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3
    async with await registry.open_game("テストゲーム") as session:
        latest_run = await session.read_latest_translation_run()
    assert latest_run is not None
    assert latest_run.total_extracted == rebuild_report.summary["indexed_count"]
    assert latest_run.pending_count == 3
