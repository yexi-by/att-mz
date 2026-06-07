"""Agent Workflow Gate 业务契约测试。"""

from __future__ import annotations

import json

from tests.agent_toolkit_contract_fixtures import *
from app.llm.schemas import ChatMessage
from app.rmmz.mv_namebox_native import scan_native_mv_virtual_namebox
from app.terminology import TerminologyPromptIndex

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
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        before_errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
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
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        after_errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )
        state = await session.read_rule_review_state(rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN)

    assert "mv_virtual_namebox_missing" in {error.code for error in before_errors}
    assert empty_rejected_report.status == "error"
    assert empty_import_report.status == "warning"
    assert "mv_virtual_namebox_missing" not in {error.code for error in after_errors}
    assert state is not None
    assert state.scope_hash == mv_virtual_namebox_rule_scope_hash_for_game_data(game_data)
    assert state.scope_hash == scan_native_mv_virtual_namebox(game_data=game_data).scope_hash
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
async def test_translate_max_items_warm_index_uses_metadata_external_rule_gate(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 翻译前置外部规则检查应消费索引元信息，不重新扫描游戏规则范围。"""
    _ = app_home_with_example_setting

    async def forbidden_batches(*args: object, **kwargs: object) -> NoReturn:
        """缺少外部规则时不能进入模型批次。"""
        _ = (args, kwargs)
        raise AssertionError("外部规则未确认时 translate --max-items 不能进入模型批次")

    async def forbidden_full_external_rule_gate(*args: object, **kwargs: object) -> NoReturn:
        """warm index 已有 scope hash 时，不应走完整 GameData 外部规则 gate。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应调用完整外部规则 gate")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    monkeypatch.setattr(TranslationHandler, "_run_prepared_translation_batches", forbidden_batches)
    monkeypatch.setattr(
        "app.application.flow_gate._external_rule_gate_errors",
        forbidden_full_external_rule_gate,
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

    assert summary.text_index_status == "used"
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


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_does_not_build_full_scope_before_sql_limit(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """translate --max-items 命中 warm index 时，前置检查不应重建完整文本范围。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        """warm index 翻译前置检查不应构建完整 Python scope。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应构建完整 TextScopeService")

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        captured["item_count"] = sum(len(batch.items) for batch in batches)
        return TranslationRunState(
            total_batch_count=len(batches),
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
    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)
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
    assert summary.text_index_status == "used"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_uses_prechecked_source_branch_gates(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 已预检源码支线时，不应重新扫描插件源码和非标准 data gate。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

    async def forbidden_plugin_source_gate(*args: object, **kwargs: object) -> NoReturn:
        """warm index 已预检时不应重新运行插件源码 gate。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应重新运行插件源码 gate")

    async def forbidden_nonstandard_data_gate(*args: object, **kwargs: object) -> NoReturn:
        """warm index 已预检时不应重新运行非标准 data gate。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应重新运行非标准 data gate")

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        captured["item_count"] = sum(len(batch.items) for batch in batches)
        return TranslationRunState(
            total_batch_count=len(batches),
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
    monkeypatch.setattr("app.application.flow_gate._plugin_source_rule_gate_errors", forbidden_plugin_source_gate)
    monkeypatch.setattr("app.application.flow_gate._nonstandard_data_rule_gate_errors", forbidden_nonstandard_data_gate)
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

    assert summary.text_index_status == "used"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 已预检全部 GameData 相关 gate 后，不应再加载完整游戏数据。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """已预检 warm index 的翻译前置检查不应加载完整 GameData。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应加载完整 GameData")

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        captured["item_count"] = sum(len(batch.items) for batch in batches)
        return TranslationRunState(
            total_batch_count=len(batches),
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
    monkeypatch.setattr(TranslationHandler, "_load_session_game_data", forbidden_game_data_load)
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

    assert summary.text_index_status == "used"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_uses_placeholder_gate_metadata(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 前置检查应复用索引里的占位符 gate 摘要，不重扫候选。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

    def forbidden_placeholder_scan(*args: object, **kwargs: object) -> NoReturn:
        """warm index 已有占位符 gate 元信息后不应扫描普通候选。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应重新扫描普通占位符候选")

    def forbidden_structured_placeholder_scan(*args: object, **kwargs: object) -> NoReturn:
        """warm index 已有占位符 gate 元信息后不应扫描结构化候选。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应重新扫描结构化占位符候选")

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        captured["item_count"] = sum(len(batch.items) for batch in batches)
        return TranslationRunState(
            total_batch_count=len(batches),
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
    monkeypatch.setattr(
        "app.application.flow_gate.collect_native_placeholder_candidate_details",
        forbidden_placeholder_scan,
    )
    monkeypatch.setattr(
        "app.application.flow_gate.collect_native_structured_placeholder_candidate_details",
        forbidden_structured_placeholder_scan,
    )
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

    assert summary.text_index_status == "used"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_uses_text_scope_gate_metadata(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 前置检查应复用索引里的 text-scope gate 摘要。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

    def forbidden_text_scope_gate(*args: object, **kwargs: object) -> NoReturn:
        """warm index 已有 text-scope gate 摘要后不应回到 Python scope gate。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应调用 Python text-scope gate")

    def forbidden_text_scope_restore(*args: object, **kwargs: object) -> NoReturn:
        """warm index 已预检路径不应把全部索引项还原成 TextScopeResult。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应还原完整 TextScopeResult")

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        captured["item_count"] = sum(len(batch.items) for batch in batches)
        return TranslationRunState(
            total_batch_count=len(batches),
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
    monkeypatch.setattr("app.application.flow_gate._text_scope_gate_errors", forbidden_text_scope_gate)
    import app.application.handler as handler_module

    assert not hasattr(handler_module, "text_index_items_to_scope")
    _ = forbidden_text_scope_restore
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

    assert summary.text_index_status == "used"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_uses_sql_pending_count_without_full_rows(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 翻译总 pending 摘要应使用 SQL 计数，不读取全部 rows。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

    async def forbidden_full_index_rows(*args: object, **kwargs: object) -> NoReturn:
        """warm index 翻译总 pending 不应读取全部索引行。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应读取全部 text index rows")

    def forbidden_native_scope_gate(*args: object, **kwargs: object) -> NoReturn:
        """warm index 翻译总 pending 不应调用 Rust scope gate。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应调用 Rust evaluate_scope_gate")

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        captured["item_count"] = sum(len(batch.items) for batch in batches)
        return TranslationRunState(
            total_batch_count=len(batches),
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
    indexed_count = rebuild_report.summary["indexed_count"]
    assert isinstance(indexed_count, int)
    async with await registry.open_game("テストゲーム") as session:
        existing_item = (await session.read_pending_text_index_items(limit=1))[0]
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=existing_item.location_path,
                    item_type=existing_item.item_type,
                    role=existing_item.role,
                    original_lines=existing_item.original_lines,
                    source_line_paths=existing_item.source_line_paths,
                    translation_lines=["已保存译文"],
                )
            ]
        )
    monkeypatch.setattr(TargetGameSession, "read_text_index_items", forbidden_full_index_rows)
    monkeypatch.setattr("app.text_index.evaluate_native_scope_gate", forbidden_native_scope_gate, raising=False)
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

    assert summary.total_pending_count == indexed_count - 1
    assert summary.pending_count == 3
    assert captured["item_count"] == 3


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_skips_pending_rows_when_sql_pending_zero(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 已无 pending 时，应在读取小批 rows 前早退。"""
    _ = app_home_with_example_setting

    async def forbidden_pending_rows(*args: object, **kwargs: object) -> NoReturn:
        """SQL pending 总数为 0 时不应读取 pending 小批 rows。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 无 pending 时不应读取 pending rows")

    async def forbidden_prepared_batches(*args: object, **kwargs: object) -> NoReturn:
        """无 pending 时不应进入模型批次准备后的运行阶段。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 无 pending 时不应启动翻译批次")

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
    async with await registry.open_game("テストゲーム") as session:
        pending_items = await session.read_pending_text_index_items(limit=None)
        assert pending_items
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=item.original_lines,
                    source_line_paths=item.source_line_paths,
                    translation_lines=["已保存译文"],
                )
                for item in pending_items
            ]
        )

    monkeypatch.setattr(TargetGameSession, "read_pending_text_index_items", forbidden_pending_rows)
    monkeypatch.setattr(TranslationHandler, "_run_prepared_translation_batches", forbidden_prepared_batches)

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

    assert summary.text_index_status == "used"
    assert summary.pending_count == 0
    assert summary.total_pending_count == 0
    async with await registry.open_game("テストゲーム") as session:
        assert await session.read_latest_translation_run() is None


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_applies_max_batches_while_building_batches(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 翻译应在批次构建阶段应用 max_batches，避免构建被丢弃批次。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

    def one_batch_per_source_file(
        *,
        translation_data: TranslationData,
        token_size: int,
        factor: float,
        max_command_items: int,
        system_prompt: str,
        text_rules: TextRules,
        terminology_prompt_index: object | None = None,
    ) -> list[TranslationBatch]:
        """测试替身：每个来源文件只产出一个批次，第二个来源文件即视为过量构建。"""
        _ = (token_size, factor, max_command_items, system_prompt, text_rules, terminology_prompt_index)
        captured["iter_call_count"] = captured.get("iter_call_count", 0) + 1
        if captured["iter_call_count"] > 1:
            raise AssertionError("translate --max-batches=1 不应继续构建后续来源文件的批次")
        item = translation_data.translation_items[0]
        return [
            TranslationBatch(
                items=[item],
                prompt_ids_by_location_path={item.location_path: "1"},
                messages=[ChatMessage(role="user", text="translate 1")],
            )
        ]

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
    async with await registry.open_game("テストゲーム") as session:
        pending_items = await session.read_pending_text_index_items(limit=6)
    assert len({item.source_file for item in pending_items}) > 1

    monkeypatch.setattr(
        "app.application.use_cases.translation_run.iter_translation_context_batches",
        one_batch_per_source_file,
    )
    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", run_batches_with_prepared_state)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=6, max_batches=1),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    assert summary.text_index_status == "used"
    assert captured["iter_call_count"] == 1
    assert captured["batch_count"] == 1
    assert captured["item_count"] == 1


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_rejects_non_positive_internal_max_batches(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
) -> None:
    """内部调用传入非正 max_batches 时必须显式失败。"""
    _ = app_home_with_example_setting

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

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(ValueError, match="max_batches 必须是正整数"):
            _ = await handler.translate_text(
                game_title="テストゲーム",
                setting_overrides=None,
                custom_placeholder_rules_text=None,
                run_limits=TranslationRunLimits(max_items=3, max_batches=0),
                callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
            )
    finally:
        await handler.close()


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_skips_empty_terminology_prompt_index(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 小批翻译在空术语表时不应构建无可注入内容的 prompt 索引。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

    def forbidden_prompt_index_build(*args: object, **kwargs: object) -> NoReturn:
        """空正文术语表不会产生可注入术语，不应再构建 prompt 索引。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 空术语表不应构建 TerminologyPromptIndex")

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        captured["batch_count"] = len(batches)
        captured["item_count"] = sum(len(batch.items) for batch in batches)
        captured["terminology_section_count"] = sum(
            1
            for batch in batches
            for message in batch.messages
            if message.role == "user" and "[[术语表]]" in message.text
        )
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

    monkeypatch.setattr(
        "app.application.handler.TerminologyPromptIndex.from_glossary",
        forbidden_prompt_index_build,
    )
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

    assert summary.text_index_status == "used"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3
    assert captured["terminology_section_count"] == 0


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_prunes_unmatched_terminology_before_prompt_index(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 小批翻译只为本轮 pending 可能命中的术语构建 prompt 索引。"""
    _ = app_home_with_example_setting
    _replace_first_common_event_text(minimal_game_dir, "火の術を使う。")
    captured: dict[str, object] = {}
    original_from_glossary = TerminologyPromptIndex.from_glossary

    def capture_prompt_index_glossary(
        cls: type[TerminologyPromptIndex],
        glossary: TerminologyGlossary,
        game_data: GameData | None = None,
    ) -> TerminologyPromptIndex:
        """记录传入 prompt 索引的术语表，仍用真实索引生成 prompt。"""
        _ = cls
        captured["glossary_terms"] = set(glossary.terms)
        return original_from_glossary(glossary, game_data=game_data)

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        batch_count = len(batches)
        item_count = sum(len(batch.items) for batch in batches)
        captured["batch_count"] = batch_count
        captured["item_count"] = item_count
        captured["user_prompts"] = [
            message.text
            for batch in batches
            for message in batch.messages
            if message.role == "user"
        ]
        return TranslationRunState(
            total_batch_count=batch_count,
            total_item_count=item_count,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(
                terms={
                    "火の術": "火术",
                    "海の術": "海术",
                }
            ),
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"

    monkeypatch.setattr(
        TerminologyPromptIndex,
        "from_glossary",
        classmethod(capture_prompt_index_glossary),
    )
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

    user_prompts = cast(list[str], captured["user_prompts"])
    joined_prompt = "\n".join(user_prompts)
    assert summary.text_index_status == "used"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3
    assert captured["glossary_terms"] == {"火の術"}
    assert "火の術 => 火术" in joined_prompt
    assert "海の術 => 海术" not in joined_prompt


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_restores_map_display_name_terminology(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 小批翻译应从 text index 还原地图名，供场景和术语 prompt 使用。"""
    _ = app_home_with_example_setting
    captured: dict[str, object] = {}

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index 补齐地图名术语时不应回到完整 GameData 加载。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应加载完整 GameData 补地图名术语")

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        batch_count = len(batches)
        item_count = sum(len(batch.items) for batch in batches)
        captured["item_count"] = item_count
        captured["user_prompts"] = [
            message.text
            for batch in batches
            for message in batch.messages
            if message.role == "user"
        ]
        return TranslationRunState(
            total_batch_count=batch_count,
            total_item_count=item_count,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(terms={"始まりの町": "起始之镇"}),
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        pending_items = await session.read_pending_text_index_items(limit=None)
    map_item_limit = next(
        index + 1
        for index, item in enumerate(pending_items)
        if item.source_file == "Map001.json"
    )

    monkeypatch.setattr(TranslationHandler, "_load_session_game_data", forbidden_game_data_load)
    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", run_batches_with_prepared_state)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=map_item_limit),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    user_prompts = cast(list[str], captured["user_prompts"])
    joined_prompt = "\n".join(user_prompts)
    assert summary.text_index_status == "used"
    assert summary.pending_count == map_item_limit
    assert captured["item_count"] == map_item_limit
    assert "地图：始まりの町" in joined_prompt
    assert "始まりの町 => 起始之镇" in joined_prompt


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_restores_database_entry_name_terminology(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 小批翻译应从 text index 还原数据库条目名称术语。"""
    _ = app_home_with_example_setting
    captured: dict[str, object] = {}
    original_from_glossary = TerminologyPromptIndex.from_glossary

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index 补齐数据库条目名称术语时不应回到完整 GameData 加载。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应加载完整 GameData 补数据库条目名称术语")

    def capture_prompt_index_glossary(
        cls: type[TerminologyPromptIndex],
        glossary: TerminologyGlossary,
        game_data: GameData | None = None,
    ) -> TerminologyPromptIndex:
        """记录传入 prompt 索引的术语表，仍用真实索引生成 prompt。"""
        _ = cls
        captured["glossary_terms"] = set(glossary.terms)
        return original_from_glossary(glossary, game_data=game_data)

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        batch_count = len(batches)
        item_count = sum(len(batch.items) for batch in batches)
        captured["item_count"] = item_count
        captured["user_prompts"] = [
            message.text
            for batch in batches
            for message in batch.messages
            if message.role == "user"
        ]
        return TranslationRunState(
            total_batch_count=batch_count,
            total_item_count=item_count,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(
                terms={
                    "火の術": "火术",
                    "海の術": "海术",
                }
            ),
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        pending_items = await session.read_pending_text_index_items(limit=None)
    skill_item_limit = next(
        index + 1
        for index, item in enumerate(pending_items)
        if item.location_path == "Skills.json/1/description"
    )

    monkeypatch.setattr(TranslationHandler, "_load_session_game_data", forbidden_game_data_load)
    monkeypatch.setattr(
        TerminologyPromptIndex,
        "from_glossary",
        classmethod(capture_prompt_index_glossary),
    )
    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", run_batches_with_prepared_state)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=skill_item_limit),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    user_prompts = cast(list[str], captured["user_prompts"])
    joined_prompt = "\n".join(user_prompts)
    assert summary.text_index_status == "used"
    assert summary.pending_count == skill_item_limit
    assert captured["item_count"] == skill_item_limit
    assert captured["glossary_terms"] == {"火の術"}
    assert "火の術 => 火术" in joined_prompt
    assert "海の術 => 海术" not in joined_prompt


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_restores_system_field_terminology(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 小批翻译应从 text index 还原 System 类型数组术语。"""
    _ = app_home_with_example_setting
    captured: dict[str, object] = {}
    original_from_glossary = TerminologyPromptIndex.from_glossary

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index 补齐 System 字段术语时不应回到完整 GameData 加载。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index 不应加载完整 GameData 补 System 字段术语")

    def capture_prompt_index_glossary(
        cls: type[TerminologyPromptIndex],
        glossary: TerminologyGlossary,
        game_data: GameData | None = None,
    ) -> TerminologyPromptIndex:
        """记录传入 prompt 索引的术语表，仍用真实索引生成 prompt。"""
        _ = cls
        captured["glossary_terms"] = set(glossary.terms)
        return original_from_glossary(glossary, game_data=game_data)

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，不消耗真实模型额度。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        batch_count = len(batches)
        item_count = sum(len(batch.items) for batch in batches)
        captured["item_count"] = item_count
        captured["user_prompts"] = [
            message.text
            for batch in batches
            for message in batch.messages
            if message.role == "user"
        ]
        captured["batch_prompts"] = [
            (
                {item.location_path for item in batch.items},
                next((message.text for message in batch.messages if message.role == "user"), ""),
            )
            for batch in batches
        ]
        return TranslationRunState(
            total_batch_count=batch_count,
            total_item_count=item_count,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(
                terms={
                    "魔法": "魔法系",
                    "海": "海洋",
                }
            ),
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        pending_items = await session.read_pending_text_index_items(limit=None)
    system_item_limit = next(
        index + 1
        for index, item in enumerate(pending_items)
        if item.location_path == "System.json/gameTitle"
    )

    monkeypatch.setattr(TranslationHandler, "_load_session_game_data", forbidden_game_data_load)
    monkeypatch.setattr(
        TerminologyPromptIndex,
        "from_glossary",
        classmethod(capture_prompt_index_glossary),
    )
    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", run_batches_with_prepared_state)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=system_item_limit),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    user_prompts = cast(list[str], captured["user_prompts"])
    joined_prompt = "\n".join(user_prompts)
    assert summary.text_index_status == "used"
    assert summary.pending_count == system_item_limit
    assert captured["item_count"] == system_item_limit
    assert captured["glossary_terms"] == {"魔法"}
    batch_prompts = cast(list[tuple[set[str], str]], captured["batch_prompts"])
    system_prompts = [
        user_prompt
        for item_paths, user_prompt in batch_prompts
        if "System.json/gameTitle" in item_paths
    ]
    non_system_prompts = [
        user_prompt
        for item_paths, user_prompt in batch_prompts
        if "System.json/gameTitle" not in item_paths
    ]
    assert len(system_prompts) == 1
    assert "魔法 => 魔法系" in system_prompts[0]
    assert all("魔法 => 魔法系" not in user_prompt for user_prompt in non_system_prompts)
    assert "海 => 海洋" not in joined_prompt


@pytest.mark.asyncio
async def test_translate_max_items_warm_index_prompt_context_uses_index_metadata_only(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index prompt context 应同时从 text index 还原地图、数据库条目和 System 术语。"""
    _ = app_home_with_example_setting
    captured: dict[str, object] = {}
    original_from_glossary = TerminologyPromptIndex.from_glossary
    skills_path = minimal_game_dir / "data" / "Skills.json"
    raw_skills = cast(list[object], json.loads(skills_path.read_text(encoding="utf-8")))
    skill_record = cast(dict[str, object], raw_skills[1])
    skill_record["name"] = "秘奥義"
    _ = skills_path.write_text(json.dumps(raw_skills, ensure_ascii=False), encoding="utf-8")

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """prompt context 收尾审计不允许回到完整 GameData 加载。"""
        _ = (args, kwargs)
        raise AssertionError("translate --max-items warm index prompt context 不应加载完整 GameData")

    def capture_prompt_index_glossary(
        cls: type[TerminologyPromptIndex],
        glossary: TerminologyGlossary,
        game_data: GameData | None = None,
    ) -> TerminologyPromptIndex:
        """记录 prompt index 输入，确认 warm index 只消费索引元信息。"""
        _ = cls
        captured["prompt_index_game_data_is_none"] = game_data is None
        captured["glossary_terms"] = set(glossary.terms)
        return original_from_glossary(glossary, game_data=game_data)

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，逐批记录 prompt 与 item path。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        item_count = sum(len(batch.items) for batch in batches)
        captured["item_count"] = item_count
        captured["batch_prompts"] = [
            (
                {item.location_path for item in batch.items},
                next((message.text for message in batch.messages if message.role == "user"), ""),
            )
            for batch in batches
        ]
        return TranslationRunState(
            total_batch_count=len(batches),
            total_item_count=item_count,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(
                terms={
                    "始まりの町": "起始之镇",
                    "秘奥義": "秘奥义",
                    "魔法": "魔法系",
                    "海": "海洋",
                }
            ),
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        pending_items = await session.read_pending_text_index_items(limit=None)
    target_paths = {
        "Skills.json/1/description",
        "System.json/gameTitle",
    }
    target_indexes = [
        index
        for index, item in enumerate(pending_items)
        if item.location_path in target_paths or item.source_file == "Map001.json"
    ]
    assert target_indexes
    prompt_context_limit = max(target_indexes) + 1
    selected_original_text = "\n".join(
        line
        for item in pending_items[:prompt_context_limit]
        for line in item.original_lines
    )
    assert "秘奥義" not in selected_original_text

    monkeypatch.setattr(TranslationHandler, "_load_session_game_data", forbidden_game_data_load)
    monkeypatch.setattr(
        TerminologyPromptIndex,
        "from_glossary",
        classmethod(capture_prompt_index_glossary),
    )
    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", run_batches_with_prepared_state)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=prompt_context_limit),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    assert summary.text_index_status == "used"
    assert summary.pending_count == prompt_context_limit
    assert captured["item_count"] == prompt_context_limit
    assert captured["prompt_index_game_data_is_none"] is True
    assert captured["glossary_terms"] == {"始まりの町", "秘奥義", "魔法"}
    batch_prompts = cast(list[tuple[set[str], str]], captured["batch_prompts"])
    map_prompts = [
        prompt
        for item_paths, prompt in batch_prompts
        if any(item_path.startswith("Map001.json/") for item_path in item_paths)
    ]
    skill_prompts = [
        prompt
        for item_paths, prompt in batch_prompts
        if "Skills.json/1/description" in item_paths
    ]
    system_prompts = [
        prompt
        for item_paths, prompt in batch_prompts
        if "System.json/gameTitle" in item_paths
    ]
    assert map_prompts
    assert skill_prompts
    assert system_prompts
    assert "地图：始まりの町" in map_prompts[0]
    assert "始まりの町 => 起始之镇" in map_prompts[0]
    assert "秘奥義 => 秘奥义" in skill_prompts[0]
    assert "魔法 => 魔法系" in system_prompts[0]
    assert all("海 => 海洋" not in prompt for _item_paths, prompt in batch_prompts)
