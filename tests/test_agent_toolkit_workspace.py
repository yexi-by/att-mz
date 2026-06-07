"""Agent 工作区 manifest 和工作区校验业务契约测试。"""

from __future__ import annotations

from tests.agent_toolkit_contract_fixtures import *

from app.native_scope_index import (
    NativeRuleCandidatesResult,
    scan_native_rule_candidates as real_scan_native_rule_candidates,
)

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
    structured_rules_path = workspace / "structured-placeholder-rules.json"
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
    assert structured_rules_path.exists()
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
    assert (workspace / "nonstandard-data-risk-report.json").exists()
    assert not (workspace / "nonstandard-data").exists()
    assert "nonstandard_data_export" not in report.details
    rules = load_json_object(rules_path)
    structured_rules = load_json_object(structured_rules_path)
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
    manifest_files = ensure_json_array(coerce_json_value(manifest["files"]), "manifest.files")
    subagent_rounds = ensure_json_array(
        coerce_json_value(cast(object, workflow["subagent_rounds"])),
        "manifest.workflow.subagent_rounds",
    )
    first_round = ensure_json_object(subagent_rounds[0], "manifest.workflow.subagent_rounds[0]")
    second_round = ensure_json_object(subagent_rounds[1], "manifest.workflow.subagent_rounds[1]")
    plugin_json_string_leaf_candidate_count = report.summary["plugin_json_string_leaf_candidate_count"]
    assert rules == {r"(?i)\\F\d*\[[^\]\r\n]+\]": "[CUSTOM_FACE_PORTRAIT_{index}]"}
    assert structured_rules == {"paired_shell_rules": []}
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
    assert report.summary["structured_placeholder_rule_count"] == 0
    assert report.summary["terminology_subtask_count"] == 5
    assert str(workspace / "nonstandard-data") not in {str(value) for value in manifest_files if isinstance(value, str)}
    assert "main_agent_rounds" not in workflow
    assert len(subagent_rounds) == 2
    assert first_round["name"] == "terminology_candidates"
    assert first_round["owner"] == "主代理"
    assert "正文术语表清洗规则" in str(first_round["description"])
    assert "非字段表副本" in str(first_round["description"])
    assert second_round["name"] == "external_text_rules"
    assert "placeholder_phase" in workflow
    assert "plugin-json-string-leaf-candidates.json" in json.dumps(report.details, ensure_ascii=False)
    assert "note-tag-rules.json" in json.dumps(report.details, ensure_ascii=False)
    assert "structured-placeholder-rules.json" in json.dumps(report.details, ensure_ascii=False)


@pytest.mark.asyncio
async def test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工作区候选 manifest 和草稿共用 native 明细，不再回到旧 scanner。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    native_candidate_marker = r"\NATIVE_DRAFT[1]"
    native_call_count = 0

    def fake_native_placeholder_details(*args: object, **kwargs: object) -> JsonArray:
        nonlocal native_call_count
        _ = (args, kwargs)
        native_call_count += 1
        return [
            {
                "marker": native_candidate_marker,
                "count": 1,
                "sources": ["native-source#0"],
                "standard_covered": False,
                "custom_covered": False,
                "covered": False,
            }
        ]

    def forbidden_legacy_placeholder_scan(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("prepare-agent-workspace 普通占位符草稿不应再调用旧 Python scanner")

    monkeypatch.setattr(
        "app.agent_toolkit.services.workspace.collect_native_placeholder_candidate_details_from_entries",
        fake_native_placeholder_details,
        raising=False,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.workspace.scan_placeholder_candidates",
        forbidden_legacy_placeholder_scan,
        raising=False,
    )

    report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )

    placeholder_manifest = load_json_object(workspace / "placeholder-candidates.json")
    placeholder_details = ensure_json_object(
        coerce_json_value(placeholder_manifest["details"]),
        "placeholder_manifest.details",
    )
    candidates = ensure_json_array(
        placeholder_details["candidates"],
        "placeholder_manifest.details.candidates",
    )
    first_candidate = ensure_json_object(candidates[0], "placeholder_manifest.details.candidates[0]")
    draft_rules = load_json_object(workspace / "placeholder-rules.json")

    assert report.status == "ok"
    assert native_call_count == 1
    assert first_candidate["marker"] == native_candidate_marker
    assert list(draft_rules) == [r"\\NATIVE_DRAFT\[1\]"]
@pytest.mark.asyncio
async def test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已有插件源码规则时，工作区准备复用风险扫描结果，不在文本范围构建中二次扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "WorkspaceReuse", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "WorkspaceReuse.js").write_text(
        "const Messages = { title: '翻訳する本文' };\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        game_data = await load_game_data(
            minimal_game_dir,
            include_writable_copies=False,
            run_dialogue_probe_check=False,
        )
        scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
        file_scan = next(file_scan for file_scan in scan.files if file_scan.file_name == "WorkspaceReuse.js")
        candidate = next(candidate for candidate in scan.candidates if candidate.file_name == "WorkspaceReuse.js")
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="WorkspaceReuse.js",
                    file_hash=file_scan.file_hash,
                    selectors=[candidate.selector],
                    excluded_selectors=[],
                )
            ]
        )

    def forbidden_scope_plugin_source_scan(*args: object, **kwargs: object) -> NoReturn:
        """prepare-agent-workspace 已有扫描结果时，TextScopeService 不应再扫描插件源码。"""
        _ = (args, kwargs)
        raise AssertionError("prepare-agent-workspace 不应在文本范围构建中重复扫描插件源码")

    monkeypatch.setattr(
        "app.text_scope.builder.build_plugin_source_scan",
        forbidden_scope_plugin_source_scan,
        raising=False,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=tmp_path / "workspace",
        command_codes=None,
    )

    assert report.status == "ok"
    assert report.summary["plugin_source_rule_count"] == 1
@pytest.mark.asyncio
async def test_prepare_agent_workspace_uses_warm_text_index_without_full_scope_build(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 可用时，工作区占位符候选不再触发完整文本范围构建。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("prepare-agent-workspace 命中 warm index 时不应构建完整文本范围")

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)

    report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=tmp_path / "workspace",
        command_codes=None,
    )

    assert report.status == "ok"
    assert report.summary["translation_scope_mode"] == "text_index"
    assert report.summary["text_index_status"] == "used"
    draft_count = report.summary["placeholder_rule_draft_count"]
    assert isinstance(draft_count, int)
    assert draft_count >= 1


@pytest.mark.asyncio
async def test_validate_agent_workspace_uses_warm_text_index_without_full_scope_build(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 可用时，工作区验收不再构建完整文本范围。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    _ = await _rebuild_text_index_for_test(service)

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("validate-agent-workspace 命中 warm index 时不应构建完整文本范围")

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert "terminology_empty_translation" in {error.code for error in report.errors}
    assert "plugin_rules" in report.details
@pytest.mark.asyncio
async def test_validate_agent_workspace_skips_inactive_heavy_branch_scans(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未启动插件源码和非标准 data 支线时，工作区验收不应重复扫描这些重分支。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    manifest = load_json_object(workspace / "manifest.json")
    generated = ensure_json_object(coerce_json_value(manifest["generated"]), "manifest.generated")
    assert generated["plugin_source_high_risk"] is False
    assert generated["nonstandard_data_high_risk"] is False
    assert not (workspace / "plugin-source-rules.json").exists()
    assert not (workspace / "nonstandard-data-rules.json").exists()

    async def forbidden_nonstandard_data_scan(*args: object, **kwargs: object) -> NoReturn:
        """未启动非标准 data 支线时不应扫描非标准 data。"""
        _ = (args, kwargs)
        raise AssertionError("validate-agent-workspace 不应扫描未启动的非标准 data 支线")

    monkeypatch.setattr("app.agent_toolkit.services.workspace.build_nonstandard_data_scan", forbidden_nonstandard_data_scan)

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    error_codes = {error.code for error in report.errors}
    assert "plugin_source_rules_missing" not in error_codes
    assert "nonstandard_data_rules_missing" not in error_codes
    assert "nonstandard_data_scan_failed" not in error_codes


@pytest.mark.asyncio
async def test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码支线验收用 Rust 候选事实，不回到旧 Python 插件源码主扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "NativeValidateSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "NativeValidateSource.js").write_text(
        "Window_Base.prototype.drawText('支线验收候选', 0, 0, 320);\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        game_data = await load_game_data(
            minimal_game_dir,
            include_writable_copies=False,
            run_dialogue_probe_check=False,
        )
        scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
        file_scan = next(file_scan for file_scan in scan.files if file_scan.file_name == "NativeValidateSource.js")
        candidate = next(candidate for candidate in scan.candidates if candidate.file_name == "NativeValidateSource.js")
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="NativeValidateSource.js",
                    file_hash=file_scan.file_hash,
                    selectors=[candidate.selector],
                    excluded_selectors=[],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    native_scan_count = 0

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        nonlocal native_scan_count
        native_scan_count += 1
        return real_scan_native_rule_candidates(payload)

    def forbidden_legacy_plugin_source_scan(*args: object, **kwargs: object) -> PluginSourceScan:
        _ = (args, kwargs)
        raise AssertionError("validate-agent-workspace 不应调用旧 Python 插件源码主扫描")

    def forbidden_write_probe_plugin_source_scan(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("validate-agent-workspace 写回探针不应二次扫描插件源码 AST")

    monkeypatch.setattr(
        "app.plugin_source_text.native_scan.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
    )
    monkeypatch.setattr(
        "app.text_scope.builder.build_plugin_source_scan",
        forbidden_legacy_plugin_source_scan,
        raising=False,
    )
    monkeypatch.setattr(
        "app.text_scope.write_probe.scan_plugin_source_files_text_strict",
        forbidden_write_probe_plugin_source_scan,
        raising=False,
    )

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert native_scan_count == 1
    assert not any(error.code.startswith("plugin_source_") for error in report.errors)
    assert report.details["plugin_source_rules"]


@pytest.mark.parametrize(
    ("sample_text", "expected_candidate"),
    [
        ("◆<Alice>ｔ", "◆<Alice>ｔ"),
        ("<名前: Alraune>", "<名前: Alraune>"),
        ("<Voice id=hero name=Alice>", "<Voice id=hero name=Alice>"),
    ],
)
@pytest.mark.asyncio
async def test_validate_agent_workspace_warns_uncovered_structured_candidates(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    sample_text: str,
    expected_candidate: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工作区验收复用已抽取正文扫描结构化协议外壳候选。"""
    common_events_path = minimal_english_game_dir / "data" / "CommonEvents.json"
    raw_value = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_value), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    text_command = ensure_json_object(commands[1], "CommonEvents.json[1].list[1]")
    parameters = ensure_json_array(text_command["parameters"], "CommonEvents.json[1].list[1].parameters")
    parameters[0] = sample_text
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    _ = await service.prepare_agent_workspace(
        game_title="English Fixture Game",
        output_dir=workspace,
        command_codes=None,
    )
    structured_rules_text = (workspace / "structured-placeholder-rules.json").read_text(encoding="utf-8")
    standalone_coverage_report = await service.scan_structured_placeholder_candidates(
        game_title="English Fixture Game",
        rules_text=structured_rules_text,
    )

    async def forbidden_structured_validation(
        self: AgentToolkitService,
        *,
        game_title: str,
        rules_text: str,
        sample_texts: list[str],
    ) -> AgentReport:
        """工作区验收不应为结构化占位符校验再抽取一次全量正文。"""
        _ = (self, game_title, rules_text, sample_texts)
        raise AssertionError("validate-agent-workspace 不应重新执行结构化占位符全量校验")

    async def forbidden_structured_scan(
        self: AgentToolkitService,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """工作区验收不应为结构化占位符覆盖再抽取一次全量正文。"""
        _ = (self, game_title, rules_text)
        raise AssertionError("validate-agent-workspace 不应重新执行结构化占位符全量扫描")

    monkeypatch.setattr(
        AgentToolkitService,
        "validate_structured_placeholder_rules",
        forbidden_structured_validation,
    )
    monkeypatch.setattr(
        AgentToolkitService,
        "scan_structured_placeholder_candidates",
        forbidden_structured_scan,
    )
    report = await service.validate_agent_workspace(game_title="English Fixture Game", workspace=workspace)

    warning_codes = {warning.code for warning in report.warnings}
    coverage_summary = ensure_json_object(
        ensure_json_object(report.details["structured_placeholder_coverage"], "structured_placeholder_coverage")[
            "summary"
        ],
        "structured_placeholder_coverage.summary",
    )
    coverage_details = ensure_json_object(
        ensure_json_object(report.details["structured_placeholder_coverage"], "structured_placeholder_coverage")[
            "details"
        ],
        "structured_placeholder_coverage.details",
    )
    assert "structured_placeholder_uncovered" in warning_codes
    assert coverage_summary["report_detail_mode"] == "sampled"
    assert coverage_summary["candidate_count"] == standalone_coverage_report.summary["candidate_count"]
    assert coverage_summary["covered_count"] == standalone_coverage_report.summary["covered_count"]
    assert coverage_summary["uncovered_count"] == 1
    assert coverage_details["detail_mode"] == "sampled"
    candidates_node = ensure_json_object(
        coverage_details["candidates"],
        "structured_placeholder_coverage.details.candidates",
    )
    candidates = ensure_json_array(
        candidates_node["samples"],
        "structured_placeholder_coverage.details.candidates.samples",
    )
    assert any(
        ensure_json_object(candidate, "candidate")["candidate"] == expected_candidate
        for candidate in candidates
    )
@pytest.mark.asyncio
async def test_prepare_agent_workspace_uses_mv_event_command_default(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 工作区摘要按 356 插件命令生成，并为未确认的名字框候选生成规则轮。"""
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
    workflow = ensure_json_object(coerce_json_value(manifest["workflow"]), "manifest.workflow")
    subagent_rounds = ensure_json_array(
        coerce_json_value(cast(object, workflow["subagent_rounds"])),
        "manifest.workflow.subagent_rounds",
    )
    first_round = ensure_json_object(subagent_rounds[0], "manifest.workflow.subagent_rounds[0]")
    commands = ensure_json_array(coerce_json_value(event_commands["356"]), "event-commands.356")
    manifest_files = "\n".join(
        item
        for item in ensure_json_array(coerce_json_value(manifest["files"]), "manifest.files")
        if isinstance(item, str)
    )
    assert report.status == "ok"
    assert report.summary["engine_kind"] == "mv"
    assert report.summary["event_command_codes"] == [356]
    assert report.summary["mv_virtual_namebox_candidate_count"] == 3
    assert report.summary["mv_virtual_namebox_rule_count"] == 0
    assert report.summary["mv_virtual_namebox_workspace_active"] is True
    assert layout["engine_kind"] == "mv"
    assert "www" in str(layout["data_dir"])
    assert len(ensure_json_array(coerce_json_value(workflow["main_agent_rounds"]), "manifest.workflow.main_agent_rounds")) == 1
    assert len(subagent_rounds) == 2
    assert first_round["name"] == "terminology_candidates"
    assert "mv-virtual-namebox-candidates.json" in manifest_files
    assert "mv-virtual-namebox-rules.json" in manifest_files
    assert (workspace / "mv-virtual-namebox-candidates.json").exists()
    assert (workspace / "mv-virtual-namebox-rules.json").exists()
    mv_candidates = load_json_object(workspace / "mv-virtual-namebox-candidates.json")
    assert isinstance(mv_candidates["scope_hash"], str)
    assert isinstance(mv_candidates["speaker_requirements"], list)
    assert len(commands) == 1


@pytest.mark.asyncio
async def test_prepare_agent_workspace_includes_mv_namebox_when_current_hash_unreviewed(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """索引元信息有当前 MV hash 但未确认空规则时，工作区必须生成 MV 规则轮。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service, game_title="MVテストゲーム")

    workspace = tmp_path / "mv-workspace"
    report = await service.prepare_agent_workspace(
        game_title="MVテストゲーム",
        output_dir=workspace,
        command_codes=None,
    )

    manifest = load_json_object(workspace / "manifest.json")
    workflow = ensure_json_object(coerce_json_value(manifest["workflow"]), "manifest.workflow")
    manifest_files = "\n".join(
        item
        for item in ensure_json_array(coerce_json_value(manifest["files"]), "manifest.files")
        if isinstance(item, str)
    )
    main_agent_rounds = ensure_json_array(
        coerce_json_value(workflow.get("main_agent_rounds", [])),
        "manifest.workflow.main_agent_rounds",
    )
    subagent_rounds = ensure_json_array(
        coerce_json_value(cast(object, workflow["subagent_rounds"])),
        "manifest.workflow.subagent_rounds",
    )
    round_names: set[str] = set()
    for round_info in [*main_agent_rounds, *subagent_rounds]:
        round_name = ensure_json_object(round_info, "manifest.workflow.round").get("name")
        if isinstance(round_name, str):
            round_names.add(round_name)
    assert report.status == "ok"
    assert report.summary["engine_kind"] == "mv"
    assert report.summary["mv_virtual_namebox_workspace_active"] is True
    assert "mv_virtual_namebox_rules" in round_names
    assert "mv-virtual-namebox-candidates.json" in manifest_files
    assert "mv-virtual-namebox-rules.json" in manifest_files
    assert (workspace / "mv-virtual-namebox-candidates.json").exists()
    assert (workspace / "mv-virtual-namebox-rules.json").exists()


@pytest.mark.asyncio
async def test_validate_agent_workspace_rejects_stale_mv_namebox_candidates(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 工作区候选 scope 不匹配当前 native facts 时必须要求重新准备工作区。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "mv-workspace"
    _ = await service.prepare_agent_workspace(
        game_title="MVテストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    candidates_path = workspace / "mv-virtual-namebox-candidates.json"
    candidates_payload = load_json_object(candidates_path)
    candidates_payload["scope_hash"] = "stale-scope"
    _ = candidates_path.write_text(json.dumps(candidates_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.validate_agent_workspace(game_title="MVテストゲーム", workspace=workspace)

    assert report.status == "error"
    assert "mv_virtual_namebox_candidates_stale" in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_validate_agent_workspace_rejects_invalid_mv_namebox_candidates_contract(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 候选文件缺少 native speaker requirements 时必须显式要求重新准备工作区。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "mv-workspace"
    _ = await service.prepare_agent_workspace(
        game_title="MVテストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    candidates_path = workspace / "mv-virtual-namebox-candidates.json"
    candidates_payload = load_json_object(candidates_path)
    _ = candidates_payload.pop("speaker_requirements", None)
    _ = candidates_path.write_text(json.dumps(candidates_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.validate_agent_workspace(game_title="MVテストゲーム", workspace=workspace)

    assert report.status == "error"
    assert "mv_virtual_namebox_candidates_invalid" in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_prepare_agent_workspace_prefills_imported_database_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    filled_glossary = TerminologyGlossary(
        terms={
            source_text: translated_text
            for entries in filled_registry.as_category_map().values()
            for source_text, translated_text in entries.items()
            if translated_text.strip()
        }
    )
    game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(registry=filled_registry, glossary=filled_glossary)
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
        await session.replace_structured_placeholder_rules(
            [
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
        )

    report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    plugin_rules_text = (workspace / "plugin-rules.json").read_text(encoding="utf-8")
    note_tag_rules_text = (workspace / "note-tag-rules.json").read_text(encoding="utf-8")
    event_command_rules_text = (workspace / "event-command-rules.json").read_text(encoding="utf-8")
    standalone_plugin_report = await service.validate_plugin_rules(
        game_title="テストゲーム",
        rules_text=plugin_rules_text,
    )
    standalone_note_tag_report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=note_tag_rules_text,
    )
    standalone_event_command_report = await service.validate_event_command_rules(
        game_title="テストゲーム",
        rules_text=event_command_rules_text,
    )

    async def forbidden_plugin_revalidation(
        self: AgentToolkitService,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """工作区验收已经持有插件参数校验上下文，不应再调用全量规则校验器。"""
        _ = (self, game_title, rules_text)
        raise AssertionError("validate-agent-workspace 不应重新执行插件参数全量校验")

    async def forbidden_note_tag_revalidation(
        self: AgentToolkitService,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """工作区验收已经持有 Note 标签校验上下文，不应再调用全量规则校验器。"""
        _ = (self, game_title, rules_text)
        raise AssertionError("validate-agent-workspace 不应重新执行 Note 标签全量校验")

    async def forbidden_event_command_revalidation(
        self: AgentToolkitService,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """工作区验收已经持有事件指令校验上下文，不应再调用全量规则校验器。"""
        _ = (self, game_title, rules_text)
        raise AssertionError("validate-agent-workspace 不应重新执行事件指令全量校验")

    monkeypatch.setattr(
        AgentToolkitService,
        "validate_plugin_rules",
        forbidden_plugin_revalidation,
    )
    monkeypatch.setattr(
        AgentToolkitService,
        "validate_note_tag_rules",
        forbidden_note_tag_revalidation,
    )
    monkeypatch.setattr(
        AgentToolkitService,
        "validate_event_command_rules",
        forbidden_event_command_revalidation,
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
    structured_placeholder_rules = load_json_object(workspace / "structured-placeholder-rules.json")
    warning_codes = {warning.code for warning in validation_report.warnings}
    assert report.status == "ok"
    assert standalone_plugin_report.status == "ok"
    assert standalone_note_tag_report.status == "ok"
    assert standalone_event_command_report.status == "ok"
    assert report.summary["plugin_rule_count"] == 1
    assert report.summary["event_command_rule_count"] == 1
    assert report.summary["note_tag_rule_count"] == 1
    assert report.summary["placeholder_rule_count"] == 1
    assert report.summary["structured_placeholder_rule_count"] == 1
    assert report.summary["glossary_term_count"] == filled_glossary.term_count()
    assert prepared_registry == filled_registry
    assert prepared_glossary == filled_glossary
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
    assert structured_placeholder_rules == {
        "paired_shell_rules": [
            {
                "name": "MINI_LABEL",
                "pattern": r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
                "translatable_group": "text",
                "protected_groups": {
                    "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
                    "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
                },
            }
        ]
    }
    assert validation_report.status == "ok"
    assert ensure_json_object(
        coerce_json_value(validation_report.details["plugin_rules"]),
        "workspace plugin rules details",
    ) == standalone_plugin_report.details
    assert ensure_json_object(
        coerce_json_value(validation_report.details["note_tag_rules"]),
        "workspace note tag rules details",
    ) == standalone_note_tag_report.details
    assert ensure_json_object(
        coerce_json_value(validation_report.details["event_command_rules"]),
        "workspace event command rules details",
    ) == standalone_event_command_report.details
    assert "plugin_rules_missing" not in warning_codes
    assert "event_command_rules_missing" not in warning_codes
    assert "terminology_empty_translation" not in warning_codes
@pytest.mark.asyncio
async def test_validate_agent_workspace_reports_duplicate_translation_samples(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """工作区验收报告为字段译名表重复译名 warning 附带可审查样例。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    field_terms_path = workspace / "terminology" / "field-terms.json"
    exported_registry = TerminologyRegistry.model_validate(load_json_object(field_terms_path))
    filled_map: dict[TerminologyCategory, dict[str, str]] = {
        category: {
            source_text: f"{source_text}译"
            for source_text in entries
        }
        for category, entries in exported_registry.as_category_map().items()
    }
    field_term_keys: list[tuple[TerminologyCategory, str]] = [
        (category, source_text)
        for category, entries in filled_map.items()
        for source_text in entries
    ]
    assert len(field_term_keys) >= 2
    for category, source_text in field_term_keys[:2]:
        filled_map[category][source_text] = "共同译名"
    filled_registry = TerminologyRegistry.from_category_map(filled_map)
    _ = field_terms_path.write_text(
        f"{json.dumps(filled_registry.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )

    validation_report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)
    terminology_details = ensure_json_object(validation_report.details["terminology"], "details.terminology")
    samples = ensure_json_array(
        terminology_details["duplicate_translation_samples"],
        "details.terminology.duplicate_translation_samples",
    )
    target_sample: JsonObject | None = None
    for index, raw_sample in enumerate(samples):
        sample = ensure_json_object(raw_sample, f"duplicate_translation_samples[{index}]")
        if sample.get("translation") == "共同译名":
            target_sample = sample
            break
    assert target_sample is not None
    sources = ensure_json_array(target_sample["sources"], "duplicate_translation_samples.sources")
    first_source = ensure_json_object(sources[0], "duplicate_translation_samples.sources[0]")
    warning_codes = {warning.code for warning in validation_report.warnings}

    assert "terminology_duplicate_translation" in warning_codes
    assert len(samples) <= 10
    assert len(sources) == 2
    assert set(first_source) == {"category", "source_text"}
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
async def test_validate_agent_workspace_blocks_missing_manifest(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """工作区验收必须依赖 manifest 确认来源和事件指令编码。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    (workspace / "manifest.json").unlink()
    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert report.status == "error"
    assert "manifest_missing" in {error.code for error in report.errors}
@pytest.mark.asyncio
async def test_validate_agent_workspace_reports_long_task_stages(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """工作区验收向 CLI 报告可观测的长任务阶段。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    progress_updates: list[tuple[int, int]] = []
    advanced_steps: list[int] = []
    statuses: list[str] = []

    def set_progress(current: int, total: int) -> None:
        """记录绝对进度。"""
        progress_updates.append((current, total))

    def advance_progress(count: int) -> None:
        """记录阶段推进。"""
        advanced_steps.append(count)

    def set_status(status: str) -> None:
        """记录阶段状态。"""
        statuses.append(status)

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    _ = await service.validate_agent_workspace(
        game_title="テストゲーム",
        workspace=workspace,
        callbacks=(set_progress, advance_progress, set_status),
    )

    assert progress_updates[0] == (0, 13)
    assert sum(advanced_steps) == 13
    for expected_status in [
        "读取工作区清单",
        "加载翻译源视图",
        "读取文本范围索引",
        "校验插件规则",
        "校验非标准 data 文件规则",
        "校验结构化占位符规则",
        "汇总工作区校验报告",
    ]:
        assert expected_status in statuses
@pytest.mark.asyncio
async def test_validate_agent_workspace_respects_confirmed_empty_external_rule_states(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """工作区空规则文件必须读取数据库里的显式空规则确认状态。"""
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
    _ = (workspace / "structured-placeholder-rules.json").write_text(
        '{"paired_shell_rules": []}\n',
        encoding="utf-8",
    )
    before_report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)
    note_import_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )
    game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
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

    after_report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    before_warning_codes = {warning.code for warning in before_report.warnings}
    after_error_codes = {error.code for error in after_report.errors}
    empty_rule_warning_codes = {
        "plugin_rules_empty_needs_import_confirmation",
        "event_command_rules_empty_needs_import_confirmation",
        "note_tag_rules_empty_needs_import_confirmation",
        "placeholder_rules_empty_needs_import_confirmation",
        "structured_placeholder_rules_empty_needs_import_confirmation",
    }
    assert empty_rule_warning_codes <= before_warning_codes
    assert note_import_report.status == "warning"
    assert {warning.code for warning in note_import_report.warnings} == {"note_tag_rules_empty"}
    assert empty_rule_warning_codes.isdisjoint(after_error_codes)
@pytest.mark.asyncio
async def test_validate_agent_workspace_rejects_high_risk_empty_plugin_source_review(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """高风险插件源码空规则复用工作区扫描结果并报错。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins_json_text = plugins_text.removeprefix("var $plugins = ").rstrip(";\r\n ")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_json_text))),
        "plugins",
    )
    plugins.append({"name": "HighRiskSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
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
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    plugin_source_rules_text = (workspace / "plugin-source-rules.json").read_text(encoding="utf-8")
    standalone_plugin_source_report = await service.validate_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=plugin_source_rules_text,
    )
    async def forbidden_plugin_source_revalidation(
        self: AgentToolkitService,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """工作区验收已经持有插件源码扫描结果，不应再调用全量规则校验器。"""
        _ = (self, game_title, rules_text)
        raise AssertionError("validate-agent-workspace 不应重新执行插件源码全量校验")

    monkeypatch.setattr(
        AgentToolkitService,
        "validate_plugin_source_rules",
        forbidden_plugin_source_revalidation,
    )
    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)
    plugin_source_details = ensure_json_object(
        coerce_json_value(report.details["plugin_source_rules"]),
        "details.plugin_source_rules",
    )

    assert plugin_source_details == standalone_plugin_source_report.details
    assert "plugin_source_rules_empty_high_risk" in {error.code for error in report.errors}
@pytest.mark.asyncio
async def test_validate_agent_workspace_uses_manifest_event_command_codes_for_empty_review(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工作区验收按 manifest 里的事件指令编码确认空规则范围。"""
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(tmp_path / "app-home"))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes={999},
    )
    game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_rule_review_state(
            rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
            scope_hash=event_command_rule_scope_hash_for_command_codes(
                game_data=game_data,
                command_codes=frozenset({999}),
            ),
            reviewed_empty=True,
        )

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)
    error_codes = {error.code for error in report.errors}

    assert "event_command_rules_empty_unconfirmed" not in error_codes
    assert "event_command_rules_empty_confirmation_stale" not in error_codes
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
async def test_validate_agent_workspace_warns_uncovered_placeholder_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工作区验收复用已抽取正文扫描普通占位符覆盖。"""
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
    placeholder_rules_text = (workspace / "placeholder-rules.json").read_text(encoding="utf-8")
    standalone_validation_report = await service.validate_placeholder_rules(
        game_title="テストゲーム",
        custom_placeholder_rules_text=placeholder_rules_text,
        sample_texts=[],
    )
    standalone_coverage_report = await service.scan_placeholder_candidates(
        game_title="テストゲーム",
        custom_placeholder_rules_text=placeholder_rules_text,
    )

    async def forbidden_placeholder_revalidation(
        self: AgentToolkitService,
        *,
        game_title: str | None,
        custom_placeholder_rules_text: str | None,
        sample_texts: Sequence[str],
    ) -> AgentReport:
        """工作区验收已经持有正文上下文，不应重新执行普通占位符全量校验。"""
        _ = (self, game_title, custom_placeholder_rules_text, sample_texts)
        raise AssertionError("validate-agent-workspace 不应重新执行普通占位符全量校验")

    async def forbidden_placeholder_rescan(
        self: AgentToolkitService,
        *,
        game_title: str,
        custom_placeholder_rules_text: str | None,
    ) -> AgentReport:
        """工作区验收不应为普通占位符覆盖再抽取一次全量正文。"""
        _ = (self, game_title, custom_placeholder_rules_text)
        raise AssertionError("validate-agent-workspace 不应重新执行普通占位符全量扫描")

    monkeypatch.setattr(
        AgentToolkitService,
        "validate_placeholder_rules",
        forbidden_placeholder_revalidation,
    )
    monkeypatch.setattr(
        AgentToolkitService,
        "scan_placeholder_candidates",
        forbidden_placeholder_rescan,
    )
    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert "placeholder_uncovered" in {warning.code for warning in report.warnings}
    placeholder_details = ensure_json_object(report.details["placeholder_rules"], "placeholder_rules")
    assert placeholder_details["rules"] == standalone_validation_report.details["rules"]
    placeholder_samples = ensure_json_array(placeholder_details["samples"], "placeholder_rules.samples")
    standalone_samples = ensure_json_array(standalone_validation_report.details["samples"], "standalone.samples")
    assert placeholder_samples[: len(standalone_samples)] == standalone_samples
    placeholder_coverage = ensure_json_object(report.details["placeholder_coverage"], "placeholder_coverage")
    summary = ensure_json_object(placeholder_coverage["summary"], "placeholder_coverage.summary")
    coverage_details = ensure_json_object(placeholder_coverage["details"], "placeholder_coverage.details")
    assert summary["report_detail_mode"] == "sampled"
    assert summary["candidate_count"] == standalone_coverage_report.summary["candidate_count"]
    assert summary["covered_count"] == standalone_coverage_report.summary["covered_count"]
    assert summary["uncovered_count"] == standalone_coverage_report.summary["uncovered_count"]
    assert summary["custom_rule_count"] == 0
    assert coverage_details["detail_mode"] == "sampled"
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
async def test_validate_agent_workspace_reuses_structured_placeholder_context(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工作区验收复用已抽取正文校验结构化占位符规则。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands.insert(
        2,
        {
            "code": 401,
            "parameters": ["<Mini Label: 薬草>"],
        },
    )
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
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

    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    _ = (workspace / "structured-placeholder-rules.json").write_text(
        f"{rules_text}\n",
        encoding="utf-8",
    )
    standalone_report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=[],
    )

    async def forbidden_structured_revalidation(
        self: AgentToolkitService,
        *,
        game_title: str,
        rules_text: str,
        sample_texts: Sequence[str],
    ) -> AgentReport:
        """工作区验收已经持有正文上下文，不应再调用结构化占位符全量校验器。"""
        _ = (self, game_title, rules_text, sample_texts)
        raise AssertionError("validate-agent-workspace 不应重新执行结构化占位符全量校验")

    monkeypatch.setattr(
        AgentToolkitService,
        "validate_structured_placeholder_rules",
        forbidden_structured_revalidation,
    )
    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)
    structured_details = ensure_json_object(
        coerce_json_value(report.details["structured_placeholder_rules"]),
        "details.structured_placeholder_rules",
    )
    structured_samples = ensure_json_array(
        coerce_json_value(structured_details["samples"]),
        "details.structured_placeholder_rules.samples",
    )

    assert standalone_report.errors == []
    assert structured_details["rules"] == standalone_report.details["rules"]
    assert structured_samples
    assert any(
        ensure_json_object(sample, "structured_placeholder_rules.samples[]")["original_text"] == "<Mini Label: 薬草>"
        for sample in structured_samples
    )
