"""RPG Maker 写回计划和 native 写回助手业务契约测试。"""

from __future__ import annotations

import hashlib

from collections.abc import Callable

from app.agent_toolkit import AgentToolkitService
from app.native_write_plan import build_native_write_back_plan, build_native_write_back_setting_payload
from app.persistence.records import TextFactV2ReadFilter
from app.persistence.sql import TEXT_INDEX_ITEMS_TABLE_NAME
from app.plugin_source_text.runtime_mapping import plugin_source_runtime_hash_lines
from app.text_index import (
    TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY,
    TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY,
)

from tests.rmmz_writeback_contract_fixtures import *


async def _write_translations_from_rebuilt_text_index(
    *,
    registry: GameRegistry,
    game_title: str,
    setting_path: Path,
    text_rules: TextRules,
) -> None:
    """按 Rust 持久文本索引写入测试译文，避免旧 Python scope 成为第二事实源。"""
    rebuild_report = await AgentToolkitService(
        game_registry=registry,
        setting_path=setting_path,
    ).rebuild_text_index(game_title=game_title)
    assert rebuild_report.status == "ok"
    async with await registry.open_game(game_title) as session:
        indexed_items = await session.read_text_index_items()
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=[
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ],
                )
                for item in indexed_items
                if item.writable
            ]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "write_back",
        "rebuild_active_runtime",
        "write_terminology",
    ],
)
async def test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build(
    mode: str,
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回相关入口已有 warm index 时不应重新构建 Python 全量文本范围。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data, _setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
            registry=(
                TerminologyRegistry(speaker_names={"アリス": "爱丽丝"})
                if mode == "write_terminology"
                else None
            ),
            glossary=(
                TerminologyGlossary(terms={"アリス": "爱丽丝"})
                if mode == "write_terminology"
                else None
            ),
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        if mode != "write_terminology":
            await session.write_translation_items(
                [
                    TranslationItem(
                        location_path=item.location_path,
                        item_type=item.item_type,
                        role=item.role,
                        original_lines=[line for line in item.original_lines],
                        source_line_paths=[path for path in item.source_line_paths],
                        translation_lines=[
                            _translated_test_line_preserving_controls(line, text_rules)
                            for line in item.original_lines
                        ],
                    )
                    for item in scope.active_items()
                ]
            )

    rebuild_report = await AgentToolkitService(
        game_registry=registry,
        setting_path=setting_path,
    ).rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        """写回前检查应复用持久索引，不应重新构建 Python 全量文本范围。"""
        _ = (args, kwargs)
        raise AssertionError("写回相关命令不应重新构建 Python 全量文本范围")

    async def forbidden_full_index_rows(*args: object, **kwargs: object) -> NoReturn:
        """写回前检查应使用 SQL 摘要，不应读取全部 text index rows。"""
        _ = (args, kwargs)
        raise AssertionError("写回相关命令不应读取全部 text index rows")

    async def forbidden_writable_translation_items(*args: object, **kwargs: object) -> NoReturn:
        """写回前检查不应把当前可写索引内所有译文拉回 Python。"""
        _ = (args, kwargs)
        raise AssertionError("写回相关命令不应读取全部可写译文对象")

    async def forbidden_rust_scope_gate(*args: object, **kwargs: object) -> NoReturn:
        """写回前检查应使用 SQL 摘要，不应为 gate 还原 Rust 输入行。"""
        _ = (args, kwargs)
        raise AssertionError("写回相关命令不应调用 evaluate_text_index_scope_gate")

    captured_modes: list[str] = []
    captured_payload_count = 0

    def fake_build_native_write_back_plan(**kwargs: object) -> NativeWriteBackPlan:
        """记录 Rust 写回计划输入，并返回不写文件的最小计划。"""
        nonlocal captured_payload_count
        captured_modes.append(cast(str, kwargs["mode"]))
        setting_payload = cast(dict[str, object], kwargs["setting_payload"])
        captured_payload_count += 1
        assert "allowed_translation_paths" not in setting_payload
        return NativeWriteBackPlan(
            files=[],
            plugin_source_runtime_write_maps=[],
            font_replacement_records=[],
            summary=NativeWriteBackSummary(
                data_item_count=0,
                plugin_item_count=0,
                terminology_written_count=1 if kwargs["mode"] == "write_terminology" else 0,
                target_font_name=None,
                source_font_count=0,
                replaced_font_reference_count=0,
                font_copied=False,
                planned_file_count=0,
                skipped_file_count=0,
            ),
            timings_ms={"total": 1},
        )

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)
    monkeypatch.setattr(
        "app.persistence.text_index_records.TextIndexRecordSessionMixin.read_text_index_items",
        forbidden_full_index_rows,
    )
    monkeypatch.setattr(
        "app.persistence.translation_records.TranslationRecordSessionMixin.read_translated_items_for_writable_text_index",
        forbidden_writable_translation_items,
    )
    monkeypatch.setattr("app.text_index.evaluate_text_index_scope_gate", forbidden_rust_scope_gate)
    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_build_native_write_back_plan)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        if mode == "write_back":
            summary = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
            assert summary.data_item_count == 0
        elif mode == "rebuild_active_runtime":
            summary = await handler.rebuild_active_runtime(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
            assert summary.data_item_count == 0
        else:
            summary = await handler.write_terminology(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
            assert summary.written_count == 1
    finally:
        await handler.close()

    assert captured_modes == [mode]
    assert captured_payload_count == 1


@pytest.mark.asyncio
async def test_write_back_warm_index_rejects_saved_translation_outside_writable_text_index(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 写回必须阻止已保存译文落在当前可写索引之外。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data, _setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=[
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ],
                )
                for item in scope.active_items()
            ]
        )

    rebuild_report = await AgentToolkitService(
        game_registry=registry,
        setting_path=setting_path,
    ).rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"

    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="System.json/staleTranslation",
                    item_type="short_text",
                    role=None,
                    original_lines=["古いテキスト"],
                    source_line_paths=[],
                    translation_lines=["索引外旧译文"],
                )
            ]
        )

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        """stale gate 应使用索引 SQL 摘要，不应重建 Python 全量文本范围。"""
        _ = (args, kwargs)
        raise AssertionError("warm index stale gate 不应重建 Python 全量文本范围")

    def forbidden_native_plan(**kwargs: object) -> NoReturn:
        """stale gate 失败时不应继续生成 Rust 写回计划。"""
        _ = kwargs
        raise AssertionError("stale gate 失败时不应继续生成 Rust 写回计划")

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)
    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", forbidden_native_plan)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(WriteBackGateError, match="不在当前可写文本范围"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "index_state"),
    [
        ("write_back", "missing"),
        ("write_back", "count_mismatch"),
        ("write_back", "precheck_missing"),
        ("rebuild_active_runtime", "missing"),
        ("rebuild_active_runtime", "count_mismatch"),
        ("rebuild_active_runtime", "precheck_missing"),
        ("write_terminology", "missing"),
        ("write_terminology", "count_mismatch"),
        ("write_terminology", "precheck_missing"),
    ],
)
async def test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate(
    mode: str,
    index_state: str,
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回相关入口索引缺失或过期时应先重建，再走索引快路径。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data, _setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
            registry=TerminologyRegistry(speaker_names={"アリス": "爱丽丝"}),
            glossary=TerminologyGlossary(terms={"アリス": "爱丽丝"}),
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=[
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ],
                )
                for item in scope.active_items()
            ]
        )

    if index_state == "count_mismatch":
        rebuild_report = await AgentToolkitService(
            game_registry=registry,
            setting_path=setting_path,
        ).rebuild_text_index(game_title="テストゲーム")
        assert rebuild_report.status == "ok"
        async with await registry.open_game("テストゲーム") as session:
            _ = await session.connection.execute(
                f"""
                DELETE FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
                WHERE location_path = (
                    SELECT location_path
                    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
                    ORDER BY location_path
                    LIMIT 1
                )
                """
            )
            await session.connection.commit()
    elif index_state == "precheck_missing":
        rebuild_report = await AgentToolkitService(
            game_registry=registry,
            setting_path=setting_path,
        ).rebuild_text_index(game_title="テストゲーム")
        assert rebuild_report.status == "ok"
        async with await registry.open_game("テストゲーム") as session:
            metadata = await session.read_text_index_metadata()
            assert metadata is not None
            scope_hashes = dict(metadata.workflow_gate_scope_hashes)
            _ = scope_hashes.pop(TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY, None)
            _ = scope_hashes.pop(TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY, None)
            await session.update_text_index_workflow_gate_scope_hashes(scope_hashes)

    async def forbidden_rust_scope_gate(*args: object, **kwargs: object) -> NoReturn:
        """自动重建后写回快路径仍不应还原 Rust scope gate 输入。"""
        _ = (args, kwargs)
        raise AssertionError("写回索引自动重建后不应调用 evaluate_text_index_scope_gate")

    captured_modes: list[str] = []
    captured_payload_count = 0

    def fake_build_native_write_back_plan(**kwargs: object) -> NativeWriteBackPlan:
        """记录 Rust 写回计划输入，并返回不写文件的最小计划。"""
        nonlocal captured_payload_count
        captured_modes.append(cast(str, kwargs["mode"]))
        setting_payload = cast(dict[str, object], kwargs["setting_payload"])
        captured_payload_count += 1
        assert "allowed_translation_paths" not in setting_payload
        return NativeWriteBackPlan(
            files=[],
            plugin_source_runtime_write_maps=[],
            font_replacement_records=[],
            summary=NativeWriteBackSummary(
                data_item_count=0,
                plugin_item_count=0,
                terminology_written_count=1 if kwargs["mode"] == "write_terminology" else 0,
                target_font_name=None,
                source_font_count=0,
                replaced_font_reference_count=0,
                font_copied=False,
                planned_file_count=0,
                skipped_file_count=0,
            ),
            timings_ms={"total": 1},
        )

    monkeypatch.setattr("app.text_index.evaluate_text_index_scope_gate", forbidden_rust_scope_gate)
    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_build_native_write_back_plan)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        if mode == "write_back":
            summary = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
            assert summary.data_item_count == 0
        elif mode == "rebuild_active_runtime":
            summary = await handler.rebuild_active_runtime(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
            assert summary.data_item_count == 0
        else:
            summary = await handler.write_terminology(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
            assert summary.written_count == 1
    finally:
        await handler.close()

    assert captured_modes == [mode]
    assert captured_payload_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "write_back",
        "rebuild_active_runtime",
        "write_terminology",
    ],
)
async def test_write_related_commands_stop_when_text_index_rebuild_fails_without_fallback(
    mode: str,
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回索引自动重建失败时必须显式停止，不应继续旧慢路径或写文件计划。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        _ = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
            registry=TerminologyRegistry(speaker_names={"アリス": "爱丽丝"}),
            glossary=TerminologyGlossary(terms={"アリス": "爱丽丝"}),
        )

    async def fake_rebuild_text_index_for_write_operation(
        self: TranslationHandler,
        *,
        session: TargetGameSession,
        setting: Setting,
        setting_overrides: SettingOverrides | None,
        text_rules: TextRules,
        callbacks: tuple[
            Callable[[int, int], None],
            Callable[[int], None],
            Callable[[str], None],
        ],
    ) -> None:
        """模拟索引重建被 workflow gate 阻断。"""
        _ = (self, session, setting, setting_overrides, text_rules, callbacks)
        raise WriteBackGateError("当前游戏持久文本范围索引自动重建失败: 测试索引重建失败")

    def forbidden_native_plan(**kwargs: object) -> NoReturn:
        """重建失败时不应继续生成 Rust 写回计划。"""
        _ = kwargs
        raise AssertionError("写回索引重建失败后不应生成 Rust 写回计划")

    monkeypatch.setattr(
        TranslationHandler,
        "_rebuild_text_index_for_write_operation",
        fake_rebuild_text_index_for_write_operation,
    )
    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", forbidden_native_plan)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(WriteBackGateError, match="当前游戏持久文本范围索引自动重建失败: 测试索引重建失败"):
            if mode == "write_back":
                _ = await handler.write_back(
                    game_title="テストゲーム",
                    callbacks=(lambda _current, _total: None, lambda _count: None),
                )
            elif mode == "rebuild_active_runtime":
                _ = await handler.rebuild_active_runtime(
                    game_title="テストゲーム",
                    callbacks=(lambda _current, _total: None, lambda _count: None),
                )
            else:
                _ = await handler.write_terminology(
                    game_title="テストゲーム",
                    callbacks=(lambda _current, _total: None, lambda _count: None),
                )
    finally:
        await handler.close()


@pytest.mark.asyncio
async def test_write_back_warm_index_rejects_quality_errors_without_python_scope_build(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 写回质量 gate 应使用索引路径事实，不读取完整质量错误对象。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data, _setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        active_items = scope.active_items()
        failed_item = active_items[0]
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=[
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ],
                )
                for item in active_items
                if item.location_path != failed_item.location_path
            ]
        )
        run_record = await session.start_translation_run(
            total_extracted=len(active_items),
            pending_count=1,
            deduplicated_count=1,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path=failed_item.location_path,
                    item_type=failed_item.item_type,
                    role=failed_item.role,
                    original_lines=[line for line in failed_item.original_lines],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["无法解析模型输出"],
                    model_response="{}",
                )
            ],
        )

    rebuild_report = await AgentToolkitService(
        game_registry=registry,
        setting_path=setting_path,
    ).rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        """warm index 写回质量 gate 不应重建 Python 全量文本范围。"""
        _ = (args, kwargs)
        raise AssertionError("warm index 写回质量 gate 不应重建 Python 全量文本范围")

    async def forbidden_quality_error_object_read(*args: object, **kwargs: object) -> NoReturn:
        """warm index 写回质量 gate 不应读取完整质量错误对象。"""
        _ = (args, kwargs)
        raise AssertionError("warm index 写回质量 gate 不应读取完整质量错误对象")

    def forbidden_native_plan(**kwargs: object) -> NoReturn:
        """质量 gate 失败时不应继续生成写回计划。"""
        _ = kwargs
        raise AssertionError("质量 gate 失败时不应继续生成写回计划")

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)
    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors_by_paths",
        forbidden_quality_error_object_read,
    )
    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", forbidden_native_plan)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(WriteBackGateError, match="模型翻了但项目检查没通过"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()


@pytest.mark.asyncio
async def test_write_back_warm_index_ignores_quality_error_after_translation_saved(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 写回不应被已经保存译文修复的旧质量错误阻断。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data, _setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        active_items = scope.active_items()
        failed_item = active_items[0]
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=[
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ],
                )
                for item in active_items
            ]
        )
        run_record = await session.start_translation_run(
            total_extracted=len(active_items),
            pending_count=1,
            deduplicated_count=1,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path=failed_item.location_path,
                    item_type=failed_item.item_type,
                    role=failed_item.role,
                    original_lines=[line for line in failed_item.original_lines],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["无法解析模型输出"],
                    model_response="{}",
                )
            ],
        )

    rebuild_report = await AgentToolkitService(
        game_registry=registry,
        setting_path=setting_path,
    ).rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        """warm index 写回不应为了已修复质量错误重建 Python 全量文本范围。"""
        _ = (args, kwargs)
        raise AssertionError("warm index 写回不应重建 Python 全量文本范围")

    async def forbidden_quality_error_object_read(*args: object, **kwargs: object) -> NoReturn:
        """warm index 写回不应读取完整质量错误对象来判断已修复路径。"""
        _ = (args, kwargs)
        raise AssertionError("warm index 写回不应读取完整质量错误对象")

    captured_modes: list[str] = []

    def fake_build_native_write_back_plan(**kwargs: object) -> NativeWriteBackPlan:
        """质量错误已由保存译文修复后应继续生成 Rust 写回计划。"""
        captured_modes.append(cast(str, kwargs["mode"]))
        return NativeWriteBackPlan(
            files=[],
            plugin_source_runtime_write_maps=[],
            font_replacement_records=[],
            summary=NativeWriteBackSummary(
                data_item_count=0,
                plugin_item_count=0,
                terminology_written_count=0,
                target_font_name=None,
                source_font_count=0,
                replaced_font_reference_count=0,
                font_copied=False,
                planned_file_count=0,
                skipped_file_count=0,
            ),
            timings_ms={"total": 1},
        )

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)
    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors_by_paths",
        forbidden_quality_error_object_read,
    )
    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_build_native_write_back_plan)

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    assert summary.data_item_count == 0
    assert captured_modes == ["write_back"]


@pytest.mark.asyncio
async def test_direct_write_back_delegates_native_quality_to_rust_plan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回不再在 Python 侧重复执行 native 质量检查，由 Rust 计划统一拦截。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    _ = (app_home / "setting.toml").write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data, _setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        translated_items: list[TranslationItem] = []
        for item in scope.active_items():
            translation_lines = [
                _translated_test_line_preserving_controls(line, text_rules)
                for line in item.original_lines
            ]
            if item.location_path == "CommonEvents.json/2/0":
                translation_lines = ["测试"]
            translated_items.append(
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=translation_lines,
                )
            )
        await session.write_translation_items(translated_items)

    def forbidden_python_native_check(*args: object, **kwargs: object) -> NoReturn:
        """Python 写回前置不应再重复执行 Rust 已覆盖的 native 质量检查。"""
        _ = (args, kwargs)
        raise AssertionError("Python 写回前置不应重复执行 native 质量或协议检查")

    rust_plan_called = False

    def fake_rust_plan(*args: object, **kwargs: object) -> object:
        """模拟 Rust 写回计划统一返回质量 gate 失败。"""
        nonlocal rust_plan_called
        rust_plan_called = True
        _ = (args, kwargs)
        raise RuntimeError("写进游戏文件前检查没通过：发现 1 条译文里的游戏控制符可能被改坏")

    monkeypatch.setattr("app.application.write_back_gate.collect_native_quality_counts", forbidden_python_native_check)
    monkeypatch.setattr("app.application.write_back_gate.count_native_write_protocol_issues", forbidden_python_native_check)
    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_rust_plan)
    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="游戏控制符可能被改坏"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()

    assert rust_plan_called is True
@pytest.mark.asyncio
async def test_native_write_back_helper_applies_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通写回快路径必须应用 Rust 计划并执行事务替换。"""
    session = _NativePlanSessionStub(tmp_path)
    written_files: list[tuple[Path, str]] = []
    statuses: list[str] = []

    def fake_build_native_write_back_plan(**kwargs: object) -> NativeWriteBackPlan:
        """返回最小 Rust 写回计划，并记录调用模式。"""
        assert kwargs["mode"] == "write_back"
        content_output_dir = kwargs["content_output_dir"]
        assert isinstance(content_output_dir, Path)
        assert content_output_dir.is_dir()
        return NativeWriteBackPlan(
            files=[
                NativePlannedFile(
                    target_path=session.content_root / "data" / "System.json",
                    relative_path="data/System.json",
                    content="{\"gameTitle\":\"测试\"}\n",
                )
            ],
            plugin_source_runtime_write_maps=[],
            font_replacement_records=[],
            summary=NativeWriteBackSummary(
                data_item_count=1,
                plugin_item_count=0,
                terminology_written_count=0,
                target_font_name=None,
                source_font_count=0,
                replaced_font_reference_count=0,
                font_copied=False,
                planned_file_count=1,
                skipped_file_count=0,
            ),
            timings_ms={"total": 1, "active_runtime_audit": 12345},
        )

    def fake_apply_files(self: WritePlanApplier, plan: RuntimeWritePlan) -> None:
        """记录事务写入计划。"""
        _ = self
        for operation in plan.file_operations:
            assert operation.content is not None
            assert operation.source_path is None
            written_files.append((operation.target_path, operation.content))

    async def fake_load_active_runtime_game_data(game_path: Path, **kwargs: object) -> GameData:
        """无插件源码映射和非标准 data 规则时不应加载当前运行视图。"""
        _ = (game_path, kwargs)
        raise AssertionError("无写后审计目标时不应加载当前运行视图")

    def fake_audit_active_runtime_plugin_source_with_scan_cache(
        *args: object,
        **kwargs: object,
    ) -> NoReturn:
        """无插件源码映射时不应执行插件源码审计。"""
        _ = (args, kwargs)
        raise AssertionError("无插件源码映射时不应执行插件源码审计")

    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_build_native_write_back_plan)
    monkeypatch.setattr("app.application.handler.WritePlanApplier.apply_files", fake_apply_files)
    monkeypatch.setattr("app.application.handler.load_active_runtime_game_data", fake_load_active_runtime_game_data)
    monkeypatch.setattr(
        "app.application.handler.audit_active_runtime_plugin_source_with_scan_cache",
        fake_audit_active_runtime_plugin_source_with_scan_cache,
    )

    handler = TranslationHandler(GameRegistry(tmp_path / "db"), LLMHandler())
    try:
        summary = await handler.write_runtime_files_with_native_plan(
            session=cast(TargetGameSession, cast(object, session)),
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None, statuses.append),
            setting=cast(
                Setting,
                cast(
                    object,
                    SimpleNamespace(
                        text_rules=TextRulesSetting(),
                        write_back=WriteBackSetting(),
                    ),
                ),
            ),
            text_rules=TextRules.from_setting(TextRulesSetting()),
            mode="write_back",
            writable_location_paths=[],
            confirm_font_overwrite=False,
            success_phase="游戏文本回写完成",
        )
    finally:
        await handler.close()

    assert summary.data_item_count == 1
    assert written_files == [(session.content_root / "data" / "System.json", "{\"gameTitle\":\"测试\"}\n")]
    assert summary.post_write_audit_ms < 12345
    assert statuses == [
        "准备 Rust 写回计划输入",
        "生成 Rust 写回计划",
        "替换游戏运行文件",
        "跳过写入后的当前运行文件审计",
        "保存写入诊断映射",
    ]
    assert session.runtime_map_replace_calls == 1
    assert session.runtime_map_replace_count == 0
@pytest.mark.asyncio
async def test_direct_write_back_rejects_latest_quality_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接调用业务写回也必须拦截模型翻了但项目检查没通过的译文。"""

    async def forbidden_full_quality_error_read(*args: object, **kwargs: object) -> NoReturn:
        """写回前检查不应读取最新运行的全部质量错误明细。"""
        _ = (args, kwargs)
        raise AssertionError("写回前检查不应读取全部质量错误")

    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data = await load_game_data(minimal_game_dir)
        placeholder_record = PlaceholderRuleRecord(
            pattern_text=r"(?i)\\F\d*\[[^\]\r\n]+\]",
            placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
        )
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
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
        await session.replace_placeholder_rules([placeholder_record])
        setting = load_setting(source_language=session.source_language)
        text_rules = TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=(
                CustomPlaceholderRule.create(
                    pattern_text=placeholder_record.pattern_text,
                    placeholder_template=placeholder_record.placeholder_template,
                ),
            ),
            structured_placeholder_rules=(),
        )
        await session.replace_rule_review_state(
            rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
            scope_hash=note_tag_rule_scope_hash_for_text_rules(
                game_data=game_data,
                text_rules=text_rules,
            ),
            reviewed_empty=True,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        await session.replace_rule_review_state(
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            scope_hash=structured_placeholder_scope_hash(
                translation_data_map=scope.translation_data_map,
                structured_rules=(),
            ),
            reviewed_empty=True,
        )
        active_items = scope.active_items()
        assert active_items
        failed_item = active_items[0]
        run_record = await session.start_translation_run(
            total_extracted=len(active_items),
            pending_count=1,
            deduplicated_count=1,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path=failed_item.location_path,
                    item_type=failed_item.item_type,
                    role=failed_item.role,
                    original_lines=[line for line in failed_item.original_lines],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["无法解析模型输出"],
                    model_response="{}",
                )
            ],
        )
    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors",
        forbidden_full_quality_error_read,
    )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="项目检查没通过"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_direct_write_back_rejects_missing_workflow_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接写入游戏文件不能在外部规则未完成时静默成功。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="检查没通过"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_direct_rebuild_active_runtime_rejects_missing_workflow_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重建当前运行文件也是写文件操作，必须受同一前置规则约束。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="检查没通过"):
            _ = await handler.rebuild_active_runtime(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_direct_rebuild_active_runtime_uses_real_native_success_path(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重建当前运行文件成功路径必须穿过真实 handler 和 Rust 写回计划。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data = await load_game_data(minimal_game_dir)
        placeholder_record = PlaceholderRuleRecord(
            pattern_text=r"(?i)\\F\d*\[[^\]\r\n]+\]",
            placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
        )
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
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
        await session.replace_placeholder_rules([placeholder_record])
        setting = load_setting(source_language=session.source_language)
        text_rules = TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=(
                CustomPlaceholderRule.create(
                    pattern_text=placeholder_record.pattern_text,
                    placeholder_template=placeholder_record.placeholder_template,
                ),
            ),
            structured_placeholder_rules=(),
        )
        await session.replace_rule_review_state(
            rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
            scope_hash=note_tag_rule_scope_hash_for_text_rules(
                game_data=game_data,
                text_rules=text_rules,
            ),
            reviewed_empty=True,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        await session.replace_rule_review_state(
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            scope_hash=structured_placeholder_scope_hash(
                translation_data_map=scope.translation_data_map,
                structured_rules=(),
            ),
            reviewed_empty=True,
        )
    await _write_translations_from_rebuilt_text_index(
        registry=registry,
        game_title="テストゲーム",
        setting_path=app_home / "setting.toml",
        text_rules=text_rules,
    )

    _rewrite_json(
        minimal_game_dir / "data" / "System.json",
        {
            "gameTitle": "损坏的当前运行文件",
            "terms": {},
        },
    )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.rebuild_active_runtime(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    rebuilt_system = ensure_json_object(
        _read_test_json(minimal_game_dir / "data" / "System.json"),
        "System.json",
    )
    assert rebuilt_system["gameTitle"] == "测试"
    assert summary.data_item_count > 0
    assert summary.planned_file_count > 0
    assert summary.rust_plan_ms >= 0
    assert summary.file_replacement_ms >= 0
    assert summary.post_write_audit_ms >= 0
@pytest.mark.asyncio
async def test_write_terminology_allows_pending_body_translation_run(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """术语写回只要求术语和写入协议可用，不因正文译文未完成而失败。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        _ = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
            registry=TerminologyRegistry(speaker_names={"アリス": "爱丽丝"}),
            glossary=TerminologyGlossary(terms={"アリス": "爱丽丝"}),
        )
        _ = await session.start_translation_run(
            total_extracted=100,
            pending_count=100,
            deduplicated_count=100,
            batch_count=1,
        )

    async def forbidden_quality_error_path_read(*args: object, **kwargs: object) -> NoReturn:
        """术语写回不要求正文译文完整，不应读取待翻译正文路径上的质量错误。"""
        _ = (args, kwargs)
        raise AssertionError("术语写回不应读取待翻译正文路径上的质量错误")

    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors_by_paths",
        forbidden_quality_error_path_read,
    )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.write_terminology(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    common_events = ensure_json_array(_read_test_json(minimal_game_dir / "data" / "CommonEvents.json"), "CommonEvents")
    first_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(first_event["list"], "CommonEvents[1].list")
    name_parameters = ensure_json_array(
        ensure_json_object(commands[0], "CommonEvents[1].list[0]")["parameters"],
        "CommonEvents[1].list[0].parameters",
    )
    assert summary.written_count > 0
    assert name_parameters[4] == "爱丽丝"
@pytest.mark.asyncio
async def test_direct_write_back_ignores_excluded_plugin_source_text_issues_during_plan_audit(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rust 计划检查不把已排除的插件源码内部字符串当正文漏翻。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { category: 'カテゴリ', protocol: '\\\\TRP' };\n",
        encoding="utf-8",
    )
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    original_events = _read_test_json(common_events_path)

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data = await load_game_data(minimal_game_dir)
        placeholder_record = PlaceholderRuleRecord(
            pattern_text=r"(?i)\\F\d*\[[^\]\r\n]+\]",
            placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
        )
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
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
        await session.replace_placeholder_rules([placeholder_record])
        setting = load_setting(source_language=session.source_language)
        text_rules = TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=(
                CustomPlaceholderRule.create(
                    pattern_text=placeholder_record.pattern_text,
                    placeholder_template=placeholder_record.placeholder_template,
                ),
            ),
            structured_placeholder_rules=(),
        )
        candidate = next(
            candidate
            for candidate in build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates
            if candidate.file_name == "HardcodedText.js" and candidate.text == "カテゴリ"
        )
        plugin_source_records = build_plugin_source_rule_records_from_import(
            game_data=game_data,
            import_file=parse_plugin_source_rule_import_text(
                json.dumps(
                    [
                        {
                            "file": "HardcodedText.js",
                            "selectors": [],
                            "excluded_selectors": [candidate.selector],
                        }
                    ],
                    ensure_ascii=False,
                )
            ),
            text_rules=text_rules,
        )
        await session.replace_plugin_source_text_rules(plugin_source_records)
        await session.replace_rule_review_state(
            rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
            scope_hash=note_tag_rule_scope_hash_for_text_rules(
                game_data=game_data,
                text_rules=text_rules,
            ),
            reviewed_empty=True,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        await session.replace_rule_review_state(
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            scope_hash=structured_placeholder_scope_hash(
                translation_data_map=scope.translation_data_map,
                structured_rules=(),
            ),
            reviewed_empty=True,
        )
    await _write_translations_from_rebuilt_text_index(
        registry=registry,
        game_title="テストゲーム",
        setting_path=app_home / "setting.toml",
        text_rules=text_rules,
    )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    assert summary.data_item_count > 0
    assert _read_test_json(common_events_path) != original_events


@pytest.mark.asyncio
async def test_native_write_back_reads_mv_namebox_render_parts_not_saved_source_fields(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MV 写回必须用 v2 fact/render parts 重建源文本，不能信任旧译文记录源字段。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": [r"\n<Dan:> Hello"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_mv_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=setting_path)
    text_rules_for_translations: TextRules
    async with await registry.open_game(record.game_title) as session:
        await session.replace_mv_virtual_namebox_rules(_mv_virtual_namebox_rule_records())
        _game_data, _setting, text_rules_for_translations = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_mv_game_dir,
            registry=TerminologyRegistry(speaker_names={"Dan": "丹"}),
            glossary=TerminologyGlossary(terms={"Dan": "丹"}),
        )

    rebuild_report = await service.rebuild_text_index(game_title=record.game_title)
    assert rebuild_report.status == "ok"
    scope_key = str(rebuild_report.summary["scope_key"])

    async with await registry.open_game(record.game_title) as session:
        facts = await session.read_text_facts_v2(
            TextFactV2ReadFilter(scope_key=scope_key, domain="mv_virtual_namebox")
        )
        fact = next(item for item in facts if item.location_path == "CommonEvents.json/2/0")
        render_parts = await session.read_text_fact_render_parts_v2([fact.fact_id])
        assert "".join(part.raw_text for part in render_parts) == r"\n<Dan:> Hello"
        indexed_items = await session.read_text_index_items()
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=(
                        "旧译文记录里的错误说话人"
                        if item.location_path == fact.location_path
                        else item.role
                    ),
                    original_lines=(
                        ["OLD_SOURCE_FIELD_SHOULD_NOT_BE_USED"]
                        if item.location_path == fact.location_path
                        else [line for line in item.original_lines]
                    ),
                    source_line_paths=(
                        ["CommonEvents.json/999/999"]
                        if item.location_path == fact.location_path
                        else [path for path in item.source_line_paths]
                    ),
                    translation_lines=(
                        ["你好"]
                        if item.location_path == fact.location_path
                        else [
                            _translated_test_line_preserving_controls(line, text_rules_for_translations)
                            for line in item.original_lines
                        ]
                    ),
                )
                for item in indexed_items
                if item.writable
            ]
        )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.write_back(
            game_title=record.game_title,
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    written_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    written_event = next(
        ensure_json_object(item, "CommonEvents item")
        for item in written_events
        if isinstance(item, dict) and item.get("id") == 2
    )
    written_commands = ensure_json_array(
        written_event["list"],
        "CommonEvents[2].list",
    )
    written_line = ensure_json_array(
        ensure_json_object(written_commands[1], "CommonEvents[2].list[1]")["parameters"],
        "CommonEvents[2].list[1].parameters",
    )[0]
    assert summary.data_item_count >= 1
    assert written_line == r"\n<丹:> 你好"


@pytest.mark.asyncio
async def test_native_plugin_source_runtime_maps_use_v2_fact_hashes(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码 runtime map 的源文本 hash 必须来自 v2 fact raw_hash。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "HashEscapedText", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HashEscapedText.js").write_text(
        "const Messages = { title: '\\u539f文' };\n",
        encoding="utf-8",
    )

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        game_data, setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
        )
        candidate = next(
            candidate
            for candidate in build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates
            if candidate.file_name == "HashEscapedText.js" and candidate.text == "原文"
        )
        plugin_source_records = build_plugin_source_rule_records_from_import(
            game_data=game_data,
            import_file=parse_plugin_source_rule_import_text(
                json.dumps(
                    [
                        {
                            "file": "HashEscapedText.js",
                            "selectors": [candidate.selector],
                            "excluded_selectors": [],
                        }
                    ],
                    ensure_ascii=False,
                )
            ),
            text_rules=text_rules,
        )
        await session.replace_plugin_source_text_rules(plugin_source_records)

    service = AgentToolkitService(game_registry=registry, setting_path=setting_path)
    rebuild_report = await service.rebuild_text_index(game_title=record.game_title)
    assert rebuild_report.status == "ok"
    scope_key = str(rebuild_report.summary["scope_key"])

    async with await registry.open_game(record.game_title) as session:
        facts = await session.read_text_facts_v2(
            TextFactV2ReadFilter(scope_key=scope_key, domain="plugin_source")
        )
        fact = next(item for item in facts if item.source_file == "HashEscapedText.js")
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=fact.location_path,
                    item_type="short_text",
                    role=None,
                    original_lines=[fact.visible_text],
                    source_line_paths=[fact.location_path],
                    translation_lines=["哈希译文"],
                )
            ]
        )
        setting_payload, _font_path, _font_names = build_native_write_back_setting_payload(
            setting=setting,
            text_rules=text_rules,
            content_root=session.content_root,
            confirm_font_overwrite=False,
            writable_location_paths=None,
        )
        native_plan = build_native_write_back_plan(
            game_path=session.game_path,
            content_root=session.content_root,
            db_path=session.db_path,
            mode="write_back",
            confirm_font_overwrite=False,
            setting_payload=setting_payload,
        )

    record_map = next(
        item
        for item in native_plan.plugin_source_runtime_write_maps
        if item.location_path == fact.location_path
    )
    assert fact.raw_text == r"\u539f文"
    assert fact.visible_text == "原文"
    assert record_map.source_text_hash == fact.raw_hash
    assert record_map.source_text_hash != hashlib.sha256(fact.visible_text.encode("utf-8")).hexdigest()
    assert record_map.translation_lines_hash == plugin_source_runtime_hash_lines(["哈希译文"])


@pytest.mark.asyncio
async def test_native_write_back_blocks_stale_plugin_source_raw_selector(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码 raw selector 失效时必须阻止写回，即便可见文本没有变化。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_path = app_home / "setting.toml"
    _ = setting_path.write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "RawSelectorChanged", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source_path = plugin_source_dir / "RawSelectorChanged.js"
    _ = source_path.write_text(
        "const Messages = { title: '\\u539f文' };\n",
        encoding="utf-8",
    )

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    setting_for_plan: Setting
    text_rules_for_plan: TextRules
    async with await registry.open_game(record.game_title) as session:
        game_data, setting_for_plan, text_rules_for_plan = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
        )
        candidate = next(
            candidate
            for candidate in build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules_for_plan).candidates
            if candidate.file_name == "RawSelectorChanged.js" and candidate.text == "原文"
        )
        plugin_source_records = build_plugin_source_rule_records_from_import(
            game_data=game_data,
            import_file=parse_plugin_source_rule_import_text(
                json.dumps(
                    [
                        {
                            "file": "RawSelectorChanged.js",
                            "selectors": [candidate.selector],
                            "excluded_selectors": [],
                        }
                    ],
                    ensure_ascii=False,
                )
            ),
            text_rules=text_rules_for_plan,
        )
        await session.replace_plugin_source_text_rules(plugin_source_records)

    service = AgentToolkitService(game_registry=registry, setting_path=setting_path)
    rebuild_report = await service.rebuild_text_index(game_title=record.game_title)
    assert rebuild_report.status == "ok"
    scope_key = str(rebuild_report.summary["scope_key"])

    async with await registry.open_game(record.game_title) as session:
        facts = await session.read_text_facts_v2(
            TextFactV2ReadFilter(scope_key=scope_key, domain="plugin_source")
        )
        fact = next(item for item in facts if item.source_file == "RawSelectorChanged.js")
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=fact.location_path,
                    item_type="short_text",
                    role=None,
                    original_lines=["原文"],
                    source_line_paths=[fact.location_path],
                    translation_lines=["哈希译文"],
                )
            ]
        )
        origin_source_path = resolve_game_layout(minimal_game_dir).plugin_source_origin_dir / "RawSelectorChanged.js"
        _ = origin_source_path.write_text("const Messages = { title: '原文' };\n", encoding="utf-8")
        setting_payload, _font_path, _font_names = build_native_write_back_setting_payload(
            setting=setting_for_plan,
            text_rules=text_rules_for_plan,
            content_root=session.content_root,
            confirm_font_overwrite=False,
            writable_location_paths=None,
        )
        with pytest.raises(RuntimeError, match="插件源码 selector 已失效"):
            _ = build_native_write_back_plan(
                game_path=session.game_path,
                content_root=session.content_root,
                db_path=session.db_path,
                mode="write_back",
                confirm_font_overwrite=False,
                setting_payload=setting_payload,
            )
@pytest.mark.asyncio
async def test_direct_write_terminology_rejects_missing_workflow_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接调用术语写回也必须经过写入前流程检查。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="检查没通过"):
            _ = await handler.write_terminology(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_rebuild_active_runtime_uses_native_rebuild_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重建入口必须直接调用 Rust 重建 helper。"""
    captured_calls: list[tuple[str, bool]] = []

    async def fake_rebuild_with_native_plan(
        self: TranslationHandler,
        game_title: str,
        callbacks: tuple[object, object],
        setting_overrides: SettingOverrides | None = None,
        confirm_font_overwrite: bool = False,
    ) -> WriteBackSummary:
        """记录重建入口传入的 native helper 参数。"""
        _ = self
        _ = callbacks
        _ = setting_overrides
        captured_calls.append((game_title, confirm_font_overwrite))
        return WriteBackSummary(
            data_item_count=0,
            plugin_item_count=0,
            terminology_written_count=0,
            target_font_name=None,
            source_font_count=0,
            replaced_font_reference_count=0,
            font_copied=False,
        )

    monkeypatch.setattr(
        TranslationHandler,
        "_rebuild_active_runtime_with_native_plan",
        fake_rebuild_with_native_plan,
    )
    handler = TranslationHandler(GameRegistry(tmp_path / "db"), LLMHandler())
    try:
        _ = await handler.rebuild_active_runtime(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
            confirm_font_overwrite=True,
        )
    finally:
        await handler.close()

    assert captured_calls == [("テストゲーム", True)]
