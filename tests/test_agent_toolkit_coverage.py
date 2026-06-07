"""Agent 文本范围、候选覆盖和扫描预算业务契约测试。"""

from __future__ import annotations

from tests.agent_toolkit_contract_fixtures import *

@pytest.mark.asyncio
async def test_text_scope_and_audit_coverage_use_unified_contract(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """统一文本清单和覆盖审计暴露同一批可处理文本。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    scope_report = await service.text_scope(game_title="テストゲーム", include_write_probe=True)
    audit_report = await service.audit_coverage(game_title="テストゲーム", include_write_probe=True)

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
async def test_text_scope_and_audit_coverage_include_write_probe_does_not_call_python_probe(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include_write_probe 只保留报告标记，不回退旧 Python 写入探针。"""

    def forbidden_collect_native_write_protocol_details(*args: object, **kwargs: object) -> NoReturn:
        """text-scope/audit-coverage 不应再调用旧文本范围写入探针。"""
        _ = (args, kwargs)
        raise AssertionError("include_write_probe 不应回退 app.text_scope.write_probe")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        forbidden_collect_native_write_protocol_details,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    scope_report = await service.text_scope(game_title="テストゲーム", include_write_probe=True)
    audit_report = await service.audit_coverage(game_title="テストゲーム", include_write_probe=True)
    unwritable_items = ensure_json_array(scope_report.details["unwritable_items"], "unwritable_items")

    assert scope_report.status == "ok"
    assert scope_report.summary["unwritable_count"] == 0
    assert scope_report.summary["write_back_probe_requested"] is True
    assert scope_report.summary["write_back_probe_executed"] is False
    assert scope_report.summary["write_back_probe_mode"] == "index_writable"
    assert scope_report.summary["write_back_probe_enabled"] is False
    assert unwritable_items == []
    assert audit_report.status == "error"
    assert audit_report.summary["write_back_probe_requested"] is True
    assert audit_report.summary["write_back_probe_executed"] is False
    assert audit_report.summary["write_back_probe_mode"] == "index_writable"
    assert audit_report.summary["write_back_probe_enabled"] is False
    assert "write_probe_failed" not in {error.code for error in audit_report.errors}
    extractable_count = scope_report.summary["extractable_count"]
    assert isinstance(extractable_count, int)
    assert audit_report.summary["writable_count"] == extractable_count
@pytest.mark.asyncio
async def test_read_only_scope_reports_skip_write_probe_by_default(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只读文本范围报告默认不执行写入探针。"""

    def forbidden_write_probe(*args: object, **kwargs: object) -> NoReturn:
        """默认只读报告不应触碰写入协议探针。"""
        _ = (args, kwargs)
        raise AssertionError("只读文本范围报告默认不应执行写入探针")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        forbidden_write_probe,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending.json"

    scope_report = await service.text_scope(game_title="テストゲーム")
    audit_report = await service.audit_coverage(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")
    pending_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )

    assert scope_report.summary["write_back_probe_enabled"] is False
    assert audit_report.summary["write_back_probe_enabled"] is False
    assert quality_report.summary["write_back_probe_enabled"] is False
    assert pending_report.summary["write_back_probe_enabled"] is False


@pytest.mark.asyncio
async def test_audit_coverage_uses_warm_text_index_without_full_scope_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 audit-coverage 在 warm index 下使用索引和 SQLite 统计，不构建完整 scope。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index 覆盖审计不应触碰游戏文件加载。"""
        _ = (args, kwargs)
        raise AssertionError("warm index audit-coverage 不应加载完整游戏数据")

    async def forbidden_scope_build(*args: object, **kwargs: object) -> NoReturn:
        """warm index 覆盖审计不应构建完整文本范围。"""
        _ = (args, kwargs)
        raise AssertionError("warm index audit-coverage 不应构建完整文本范围")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await _rebuild_text_index_for_test(service)
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )
    monkeypatch.setattr(TextScopeService, "build", forbidden_scope_build)

    audit_report = await service.audit_coverage(game_title="テストゲーム")

    assert audit_report.summary["text_index_status"] == "used"
    assert audit_report.summary["extractable_count"] == rebuild_report.summary["indexed_count"]
    assert audit_report.summary["pending_count"] == rebuild_report.summary["indexed_count"]
    assert audit_report.summary["write_back_probe_enabled"] is False
    assert audit_report.status == "error"
    assert {error.code for error in audit_report.errors} == {"coverage_missing_translation"}
    assert audit_report.details["detail_mode"] == "sampled"


@pytest.mark.asyncio
async def test_text_scope_uses_warm_text_index_without_full_scope_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 text-scope 在 warm index 下从索引输出清单，不构建完整 scope。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index 文本清单不应触碰完整游戏数据加载。"""
        _ = (args, kwargs)
        raise AssertionError("warm index text-scope 不应加载完整游戏数据")

    async def forbidden_scope_build(*args: object, **kwargs: object) -> NoReturn:
        """warm index 文本清单不应构建完整文本范围。"""
        _ = (args, kwargs)
        raise AssertionError("warm index text-scope 不应构建完整文本范围")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await _rebuild_text_index_for_test(service)
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )
    monkeypatch.setattr(TextScopeService, "build", forbidden_scope_build)

    scope_report = await service.text_scope(game_title="テストゲーム")

    entries = ensure_json_array(scope_report.details["entries"], "entries")
    assert scope_report.summary["text_index_status"] == "used"
    assert scope_report.summary["entry_count"] == rebuild_report.summary["indexed_count"]
    assert scope_report.summary["extractable_count"] == rebuild_report.summary["indexed_count"]
    assert scope_report.summary["write_back_probe_enabled"] is False
    assert len(entries) == rebuild_report.summary["indexed_count"]
    assert scope_report.status == "ok"
    entry_objects = [ensure_json_object(entry, "entries[]") for entry in entries]
    assert any(
        isinstance(entry["location_path"], str) and entry["location_path"].startswith("CommonEvents.json/")
        for entry in entry_objects
    )
    assert all(entry["rule_source"] == "text_index" for entry in entry_objects)
    assert all(entry["enters_translation"] is True for entry in entry_objects)
@pytest.mark.asyncio
async def test_text_scope_reports_global_write_probe_failure(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧写入探针整体不可用时不影响 index 报告。"""

    def forbidden_collect_native_write_protocol_details(*args: object, **kwargs: object) -> NoReturn:
        """text-scope/audit/quality 不应再触碰旧文本范围写入探针。"""
        _ = (args, kwargs)
        raise AssertionError("include_write_probe 不应回退 app.text_scope.write_probe")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        forbidden_collect_native_write_protocol_details,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    scope_report = await service.text_scope(game_title="テストゲーム", include_write_probe=True)
    audit_report = await service.audit_coverage(game_title="テストゲーム", include_write_probe=True)
    quality_report = await service.quality_report(game_title="テストゲーム", include_write_probe=True)

    assert scope_report.status == "ok"
    assert audit_report.status == "error"
    assert quality_report.status == "error"
    assert "write_probe_failed" not in {error.code for error in scope_report.errors}
    assert "write_probe_failed" not in {error.code for error in audit_report.errors}
    assert "write_probe_failed" not in {error.code for error in quality_report.errors}
    assert scope_report.summary["unwritable_count"] == 0
@pytest.mark.asyncio
async def test_text_scope_reports_batch_write_probe_failure_directly(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧批量探针失败不会影响 text index 输出。"""

    def forbidden_collect_native_write_protocol_details(*args: object, **kwargs: object) -> NoReturn:
        """text-scope 不应再进入旧批量写入探针。"""
        _ = (args, kwargs)
        raise AssertionError("include_write_probe 不应回退 app.text_scope.write_probe")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        forbidden_collect_native_write_protocol_details,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    scope_report = await service.text_scope(game_title="テストゲーム", include_write_probe=True)

    assert scope_report.status == "ok"
    assert scope_report.summary["write_back_probe_requested"] is True
    assert scope_report.summary["write_back_probe_executed"] is False
    assert scope_report.summary["write_back_probe_mode"] == "index_writable"
    assert scope_report.summary["write_back_probe_enabled"] is False
    assert scope_report.summary["unwritable_count"] == 0
    assert "write_probe_failed" not in {error.code for error in scope_report.errors}
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
async def test_scan_placeholder_candidates_uses_warm_text_index_without_full_scope_build(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 可用时，占位符候选扫描直接读取索引项。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("scan-placeholder-candidates 命中 warm index 时不应构建完整文本范围")

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)

    report = await service.scan_placeholder_candidates(
        game_title="テストゲーム",
        custom_placeholder_rules_text=None,
    )

    assert report.status in {"ok", "warning"}
    candidate_count = report.summary["candidate_count"]
    assert isinstance(candidate_count, int)
    assert candidate_count >= 1


@pytest.mark.asyncio
async def test_scan_placeholder_candidates_uses_native_candidate_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """扫描命令必须复用 native 普通占位符候选入口。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    def forbidden_python_scan(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("scan-placeholder-candidates 不应继续调用 Python 普通占位符扫描器")

    monkeypatch.setattr(
        "app.agent_toolkit.services.common.scan_placeholder_candidates",
        forbidden_python_scan,
    )

    report = await service.scan_placeholder_candidates(
        game_title="テストゲーム",
        custom_placeholder_rules_text='{"\\\\\\\\F\\\\[[^\\\\]]+\\\\]":"[CUSTOM_FACE_PORTRAIT_{index}]"}',
    )

    assert report.status == "ok"
    candidate_count = report.summary["candidate_count"]
    assert isinstance(candidate_count, int) and not isinstance(candidate_count, bool)
    assert candidate_count >= 1
    assert report.summary["uncovered_count"] == 0
    raw_json = report.to_json_text()
    assert r"\F[GuideA]" in raw_json
    assert "テスト一行目です" not in raw_json
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
async def test_scan_structured_placeholder_candidates_uses_native_candidate_scan(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """扫描命令必须复用 native 结构化占位符候选入口。"""
    _replace_first_common_event_text(minimal_english_game_dir, "<名前: Alraune> trailing text")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    def fake_native_structured_details(*args: object, **kwargs: object) -> JsonArray:
        """用 sentinel 明细证明扫描命令消费 native 候选入口。"""
        _ = (args, kwargs)
        return [
            {
                "location_path": "CommonEvents.json/1/list/0/parameters/0",
                "line_number": 1,
                "candidate": "<名前: Alraune>",
                "text": "<名前: Alraune>",
                "range": [0, 13],
                "covered": True,
                "covered_by": "custom_placeholder",
                "matching_rules": ["INLINE_NAME"],
                "candidate_kind": "structured_shell",
                "location_paths": ["CommonEvents.json/1/list/0/parameters/0"],
            }
        ]

    monkeypatch.setattr(
        "app.agent_toolkit.services.common.collect_native_structured_placeholder_candidate_details",
        fake_native_structured_details,
    )

    report = await service.scan_structured_placeholder_candidates(
        game_title="English Fixture Game",
        rules_text=json.dumps(
            {
                "paired_shell_rules": [
                    {
                        "name": "INLINE_NAME",
                        "pattern": r"(?P<open><名前:\s*)(?P<text>[^>\r\n]+)(?P<close>>)",
                        "translatable_group": "text",
                        "protected_groups": {
                            "open": "[CUSTOM_INLINE_NAME_OPEN_{index}]",
                            "close": "[CUSTOM_INLINE_NAME_CLOSE_{index}]",
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    assert report.status == "ok"
    assert report.summary["rule_count"] == 1
    assert report.summary["candidate_count"] == 1
    assert report.summary["covered_count"] == 1
    assert report.summary["uncovered_count"] == 0
    raw_json = report.to_json_text()
    assert "<名前: Alraune>" in raw_json
    assert "custom_placeholder" in raw_json
    assert "trailing text" not in raw_json


def test_placeholder_candidate_scan_requires_full_span_coverage() -> None:
    """覆盖扫描不能把标准短前缀当成长候选已覆盖。"""
    translation_data_map = {
        "Map001.json": TranslationData(
            display_name=None,
            translation_items=[
                TranslationItem(
                    location_path="Map001.json/1/0",
                    item_type="long_text",
                    original_lines=[r"\nn[Name]こんにちは"],
                )
            ],
        )
    }

    uncovered_candidates = scan_placeholder_candidate_spans(
        translation_data_map,
        TextRules.from_setting(TextRulesSetting()),
    )
    covered_candidates = scan_placeholder_candidate_spans(
        translation_data_map,
        TextRules.from_setting(
            TextRulesSetting(),
            custom_placeholder_rules=(
                CustomPlaceholderRule.create(
                    r"\\nn\[[^\]\r\n]+\]",
                    "[CUSTOM_PLUGIN_NAME_{index}]",
                ),
            ),
        ),
    )

    assert count_uncovered_candidates(uncovered_candidates) == 1
    assert uncovered_candidates[0].marker == r"\nn[Name]"
    assert uncovered_candidates[0].standard_covered is False
    assert count_uncovered_candidates(covered_candidates) == 0
    assert covered_candidates[0].marker == r"\nn[Name]"
    assert covered_candidates[0].custom_covered is True
