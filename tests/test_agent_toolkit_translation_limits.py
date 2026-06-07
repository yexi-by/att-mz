"""Agent 翻译小批和运行限制业务契约测试。"""

from __future__ import annotations

from tests.agent_toolkit_contract_fixtures import *

@pytest.mark.asyncio
async def test_translate_max_items_cold_rebuilds_missing_text_index(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """translate --max-items 缺索引时自动 cold rebuild，再按 SQL 限制 pending。"""
    _ = app_home_with_example_setting
    captured: dict[str, int] = {}

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

    assert summary.text_index_status == "cold_rebuilt"
    assert summary.text_index_rebuild_summary is not None
    assert summary.text_index_rebuild_summary["index_status"] == "rebuilt"
    assert summary.pending_count == 3
    assert captured["item_count"] == 3
    async with await registry.open_game("テストゲーム") as session:
        metadata = await session.read_text_index_metadata()
    assert metadata is not None
    assert summary.total_extracted_items == metadata.item_count


@pytest.mark.asyncio
async def test_translate_warm_index_uses_v2_fact_translatable_text_for_prompt(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """translate warm index 路径的模型正文必须来自 v2 fact，而不是旧索引原文。"""
    _ = app_home_with_example_setting
    captured_prompts: list[str] = []
    captured_items: list[TranslationItem] = []

    async def run_batches_with_prepared_state(*args: object, **kwargs: object) -> TranslationRunState:
        """截断到模型前，捕获已经组装好的 prompt。"""
        _ = args
        raw_batches = kwargs["batches"]
        if not isinstance(raw_batches, list):
            raise TypeError("batches 必须是列表")
        batches = cast(list[TranslationBatch], raw_batches)
        for batch in batches:
            captured_items.extend(batch.items)
            captured_prompts.extend(message.text for message in batch.messages)
        return TranslationRunState(
            total_batch_count=len(batches),
            total_item_count=sum(len(batch.items) for batch in batches),
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
        async with session.connection.execute(
            "SELECT translatable_text FROM text_facts_v2 ORDER BY domain, location_path, fact_id LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        expected_text = cast(str, row["translatable_text"])
        polluted_lines = json.dumps(
            ["RAW_SHELL_SHOULD_NOT_REACH_MODEL location_path translated_text 位置:"],
            ensure_ascii=False,
        )
        _ = await session.connection.execute(
            "UPDATE text_index_items SET original_lines = ?",
            (polluted_lines,),
        )
        await session.connection.commit()
    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", run_batches_with_prepared_state)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=1),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    joined_prompt = "\n".join(captured_prompts)
    assert summary.text_index_status == "used"
    assert summary.pending_count == 1
    assert captured_items
    assert captured_items[0].original_lines == [expected_text]
    assert expected_text in joined_prompt
    assert "RAW_SHELL_SHOULD_NOT_REACH_MODEL" not in joined_prompt
    assert "location_path" not in joined_prompt
    assert "translated_text" not in joined_prompt
    assert "位置:" not in joined_prompt
