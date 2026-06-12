"""非标准 data 文件文本扫描、导出和规则校验测试。"""

import json
from pathlib import Path
from typing import cast

import pytest

from tests.native_rule_seed import (
    seed_native_nonstandard_data_text_rules,
)

from app.agent_toolkit import AgentToolkitService
from app.agent_toolkit.reports import AgentReport
from app.application.handler import TranslationHandler, TranslationRunLimits
from app.application.flow_gate import collect_workflow_gate_errors
from app.application.use_cases.translation_run import TranslationRunState
from app.llm import LLMHandler
from app.native_scope_index import (
    NativeRuleCandidatesResult,
    scan_native_rule_candidates as real_scan_native_rule_candidates,
)
from app.nonstandard_data import (
    NonstandardDataRuleImportFile,
    NonstandardDataRuleValidationResult,
    parse_nonstandard_data_rule_import_text,
    validate_nonstandard_data_rules,
)
from app.nonstandard_data.scanner import (
    NonstandardDataScan,
    build_nonstandard_data_file_hash,
    build_nonstandard_data_scan,
)
from app.persistence import GameRegistry
from app.rmmz.game_file_view import GameFileView
from app.rmmz.json_types import coerce_json_value, ensure_json_array, ensure_json_object
from app.rmmz.loader import load_translation_source_game_data, resolve_game_layout
from app.rmmz.schema import NonstandardDataTextRuleRecord, TranslationItem
from app.rmmz.text_rules import JsonObject, TextRules
from app.utils.config_loader_utils import load_setting
from tests._native_write_plan_helper import write_data_text
from tests.agent_toolkit_contract_fixtures import (
    _install_minimal_workflow_gate_prerequisites,
    _translated_test_line_preserving_protocol_candidates,
    make_writable_current_translation_items_for_test,
    write_current_translation_items_for_test,
)
from tests.conftest import EXAMPLE_SETTING_PATH, write_json
from tests.current_text_fact_scope import rebuild_current_text_fact_scope_for_test


def _write_high_risk_nonstandard_data(game_root: Path) -> None:
    """写入测试用高风险非标准 data 文件。"""
    write_json(game_root / "data" / "UnknownPluginData.json", [{"id": 1, "name": "これは無視される"}])


def _workflow_gate_source_branch(report: object, source_branch: str) -> JsonObject:
    """读取报告中的 Rust source branch gate 摘要。"""
    if not isinstance(report, AgentReport):
        raise TypeError("report 必须是 AgentReport")
    workflow_gate = ensure_json_object(report.details["workflow_gate"], "workflow_gate")
    source_branches = ensure_json_object(workflow_gate["source_branches"], "workflow_gate.source_branches")
    return ensure_json_object(
        source_branches[source_branch],
        f"workflow_gate.source_branches.{source_branch}",
    )


@pytest.mark.asyncio
async def test_nonstandard_data_scan_uses_native_candidate_scan(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非标准 data 扫描用 Rust 候选入口筛选候选和展开叶子。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    layout = resolve_game_layout(minimal_game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    native_payloads: list[JsonObject] = []

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        native_payloads.append(payload)
        return real_scan_native_rule_candidates(payload)

    monkeypatch.setattr(
        "app.nonstandard_data.scanner.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
        raising=False,
    )

    scan = await build_nonstandard_data_scan(
        layout=layout,
        source_view=GameFileView.ACTIVE_RUNTIME,
        text_rules=text_rules,
    )

    assert len(native_payloads) == 1
    native_payload = native_payloads[0]
    assert "nonstandard_data_files" in native_payload
    assert "text_rules" in native_payload
    assert scan.high_risk
    assert [candidate.json_path for candidate in scan.candidates] == ["$[0]['name']"]
    assert scan.candidates[0].file_name == "UnknownPluginData.json"
    assert scan.candidates[0].source_text == "これは無視される"
    assert scan.file_scans[0].string_leaf_count == 1
    assert scan.file_scans[0].candidate_count == 1
    leaves = scan.leaves_by_file["UnknownPluginData.json"]
    assert {leaf.path for leaf in leaves} == {"$[0]['id']", "$[0]['name']"}


@pytest.mark.asyncio
async def test_nonstandard_data_agent_exports_candidates_and_sources(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """导出命令生成候选报告和原始非标准 JSON 副本。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_dir = tmp_path / "workspace" / "nonstandard-data"

    report = await service.export_nonstandard_data_json(
        game_title="テストゲーム",
        output_dir=output_dir,
    )
    raw_payload = output_dir / "candidates.json"
    source_copy = output_dir / "source" / "UnknownPluginData.json"
    raw_json = cast(object, json.loads(raw_payload.read_text(encoding="utf-8")))
    payload = ensure_json_object(
        coerce_json_value(raw_json),
        "candidates.json",
    )
    candidates = ensure_json_array(payload["candidates"], "candidates")
    first_candidate = ensure_json_object(candidates[0], "candidates[0]")

    assert report.status == "warning"
    assert report.summary["candidate_count"] == 1
    assert raw_payload.is_file()
    assert source_copy.is_file()
    assert first_candidate["file"] == "UnknownPluginData.json"
    assert first_candidate["json_path"] == "$[0]['name']"
    assert "natural_text_candidate" not in first_candidate


@pytest.mark.asyncio
async def test_prepare_agent_workspace_exports_nonstandard_data_branch(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """总工作区会写出非标准 data 风险报告、候选输入和高风险规则草稿。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"

    report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    risk_report = ensure_json_object(
        coerce_json_value(
            cast(object, json.loads((workspace / "nonstandard-data-risk-report.json").read_text(encoding="utf-8")))
        ),
        "nonstandard-data-risk-report.json",
    )
    candidates_payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads((workspace / "nonstandard-data" / "candidates.json").read_text(encoding="utf-8")))),
        "nonstandard-data/candidates.json",
    )

    assert report.status == "ok"
    assert report.summary["nonstandard_data_high_risk"] is True
    assert "nonstandard_data_export" in report.details
    assert (workspace / "nonstandard-data-rules.json").read_text(encoding="utf-8").strip() == "[]"
    assert (workspace / "nonstandard-data" / "source" / "UnknownPluginData.json").is_file()
    assert ensure_json_object(risk_report["summary"], "summary")["candidate_count"] == 1
    assert len(ensure_json_array(candidates_payload["candidates"], "candidates")) == 1


@pytest.mark.asyncio
async def test_validate_agent_workspace_blocks_empty_nonstandard_data_review(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """高风险非标准 data 工作区没有全量归类时，总体验收报错。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    workspace = tmp_path / "workspace"
    _ = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    assert report.status == "error"
    assert "nonstandard_data_rules_invalid" in {error.code for error in report.errors}


@pytest.mark.asyncio
async def test_nonstandard_data_rules_validate_uses_native_rule_coverage(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """规则覆盖统计复用 native candidates/leaves，不走 Python 路径模板展开。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    layout = resolve_game_layout(minimal_game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    scan = await build_nonstandard_data_scan(
        layout=layout,
        source_view=GameFileView.ACTIVE_RUNTIME,
        text_rules=text_rules,
    )
    import_file = parse_nonstandard_data_rule_import_text(
        json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                    "skipped": False,
                }
            ],
            ensure_ascii=False,
        )
    )
    native_payloads: list[JsonObject] = []

    def counting_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        native_payloads.append(payload)
        return real_scan_native_rule_candidates(payload)

    monkeypatch.setattr(
        "app.nonstandard_data.rules.scan_native_rule_candidates",
        counting_scan_native_rule_candidates,
        raising=False,
    )

    validation = validate_nonstandard_data_rules(scan=scan, import_file=import_file)

    assert len(native_payloads) == 1
    assert "nonstandard_data_rule_coverage" in native_payloads[0]
    assert validation.rule_count == 1
    assert validation.reviewed_candidate_count == 1
    assert validation.unreviewed_candidate_paths == ()
    assert validation.details["translated_candidates"] == [
        {"file": "UnknownPluginData.json", "json_path": "$[0]['name']"}
    ]


@pytest.mark.asyncio
async def test_nonstandard_data_rules_reject_unreviewed_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """高风险候选没有全量归类时，规则校验报告返回 error。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text="[]",
    )

    assert report.status == "error"
    assert report.errors[0].code == "nonstandard_data_rules_invalid"
    assert "未全量归类" in report.errors[0].message


@pytest.mark.asyncio
async def test_nonstandard_data_rules_allow_file_skip_with_warning(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """用户按文件确认跳过后，校验通过但持续 warning。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": [],
                    "excluded_paths": [],
                    "skipped": True,
                }
            ],
            ensure_ascii=False,
        ),
    )

    assert report.status == "warning"
    assert report.summary["skipped_file_count"] == 1
    assert report.warnings[0].code == "nonstandard_data_files_skipped"


@pytest.mark.asyncio
async def test_nonstandard_data_skipped_warning_persists_in_reports(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """导入跳过规则后，文本范围、覆盖审计和质量报告持续提示风险。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    _ = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": [],
                    "excluded_paths": [],
                    "skipped": True,
                }
            ],
            ensure_ascii=False,
        ),
    )
    text_scope_report = await service.text_scope(game_title="テストゲーム")
    audit_report = await service.audit_coverage(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert "nonstandard_data_files_skipped" in {warning.code for warning in text_scope_report.warnings}
    assert "nonstandard_data_files_skipped" in {warning.code for warning in audit_report.warnings}
    assert "nonstandard_data_files_skipped" in {warning.code for warning in quality_report.warnings}
    assert text_scope_report.summary["nonstandard_data_skipped_file_count"] == 1
    assert audit_report.summary["nonstandard_data_skipped_file_count"] == 1
    assert quality_report.summary["nonstandard_data_skipped_file_count"] == 1


@pytest.mark.asyncio
async def test_nonstandard_data_rules_import_persists_records(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """导入规则会保存当前源文件哈希和路径分类。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    validation_count = 0

    def counting_validate_nonstandard_data_rules(
        *,
        scan: NonstandardDataScan,
        import_file: NonstandardDataRuleImportFile,
    ) -> NonstandardDataRuleValidationResult:
        nonlocal validation_count
        validation_count += 1
        return validate_nonstandard_data_rules(scan=scan, import_file=import_file)

    monkeypatch.setattr(
        "app.agent_toolkit.services.nonstandard_data.validate_nonstandard_data_rules",
        counting_validate_nonstandard_data_rules,
    )

    report = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                    "skipped": False,
                }
            ],
            ensure_ascii=False,
        ),
    )

    async with await registry.open_game("テストゲーム") as session:
        records = await session.read_nonstandard_data_text_rules()
        snapshot_records = await session.read_source_snapshot_records()
    origin_text = (minimal_game_dir / "data_origin" / "UnknownPluginData.json").read_bytes().decode("utf-8")

    assert report.status == "ok"
    assert validation_count == 1
    assert (minimal_game_dir / "data_origin" / "UnknownPluginData.json").is_file()
    assert "data_origin/UnknownPluginData.json" in {record.relative_path for record in snapshot_records}
    assert records == [
        NonstandardDataTextRuleRecord(
            file_name="UnknownPluginData.json",
            file_hash=build_nonstandard_data_file_hash(origin_text),
            path_templates=["$[*]['name']"],
            excluded_path_templates=[],
            skipped=False,
        )
    ]


@pytest.mark.asyncio
async def test_nonstandard_data_workflow_gate_blocks_until_rules_imported(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """正文翻译前置检查会阻断未处理的高风险非标准 data 文件。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    game_data = await load_translation_source_game_data(minimal_game_dir)

    async with await registry.open_game("テストゲーム") as session:
        before_scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        before_errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=before_scope,
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    import_report = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                    "skipped": False,
                }
            ],
            ensure_ascii=False,
        ),
    )
    async with await registry.open_game("テストゲーム") as session:
        after_scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        after_errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=after_scope,
        )

    assert "nonstandard_data_high_risk" in {error.code for error in before_errors}
    assert import_report.status == "ok"
    assert "nonstandard_data_high_risk" not in {error.code for error in after_errors}


@pytest.mark.asyncio
async def test_nonstandard_data_import_cold_rebuild_translate_and_write_back_share_rust_facts(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非标准 data 规则导入后，翻译和写回共享冷重建保存的 Rust gate facts。"""
    _ = app_home_with_example_setting
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    import_report = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                }
            ],
            ensure_ascii=False,
        ),
    )
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")

    async def fake_run_text_translation_batches(*args: object, **kwargs: object) -> TranslationRunState:
        """截断真实模型调用，只验证 translate 入口已通过 indexed gate。"""
        _ = (args, kwargs)
        return TranslationRunState(total_batch_count=0, total_item_count=0)

    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", fake_run_text_translation_batches)
    translate_handler = TranslationHandler(registry, LLMHandler())
    try:
        translate_summary = await translate_handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=1),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await translate_handler.close()

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
        stored_nonstandard_gate = ensure_json_object(
            metadata.workflow_gate_facts["nonstandard_data"],
            "metadata.workflow_gate_facts.nonstandard_data",
        )
    quality_report = await service.quality_report(game_title="テストゲーム")
    write_handler = TranslationHandler(registry, LLMHandler())
    try:
        write_summary = await write_handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await write_handler.close()
    async with await registry.open_game("テストゲーム") as session:
        metadata_after_write = await session.read_text_index_metadata()
        assert metadata_after_write is not None
        stored_nonstandard_gate_after_write = ensure_json_object(
            metadata_after_write.workflow_gate_facts["nonstandard_data"],
            "metadata_after_write.workflow_gate_facts.nonstandard_data",
        )
    workflow_gate = ensure_json_object(quality_report.details["workflow_gate"], "workflow_gate")
    quality_nonstandard_gate = _workflow_gate_source_branch(quality_report, "nonstandard_data")

    assert import_report.status == "ok"
    assert rebuild_report.status == "ok"
    assert translate_summary.text_index_status == "used"
    assert translate_summary.blocked_reason is None
    assert workflow_gate["source"] == "rust_text_index_gate_facts"
    assert quality_nonstandard_gate["status"] == "pass"
    assert quality_nonstandard_gate["scope_hash"] == stored_nonstandard_gate["scope_hash"]
    assert stored_nonstandard_gate_after_write["scope_hash"] == stored_nonstandard_gate["scope_hash"]
    assert write_summary.data_item_count > 0


@pytest.mark.asyncio
async def test_nonstandard_data_workflow_gate_rejects_stale_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """源文件变化后，旧规则必须重新导出并导入。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    game_data = await load_translation_source_game_data(minimal_game_dir)

    async with await registry.open_game("テストゲーム") as session:
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        await seed_native_nonstandard_data_text_rules(session,
            [
                NonstandardDataTextRuleRecord(
                    file_name="UnknownPluginData.json",
                    file_hash="stale-hash",
                    path_templates=["$[*]['name']"],
                )
            ]
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert "stale_nonstandard_data_rules" in {error.code for error in errors}


@pytest.mark.asyncio
async def test_nonstandard_data_rules_enter_unified_text_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """已导入的非标准 data 路径会进入统一文本清单。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                }
            ],
            ensure_ascii=False,
        ),
    )
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)

    async with await registry.open_game("テストゲーム") as session:
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )

    entry = next(
        item
        for item in scope.entries
        if item.location_path.startswith("nonstandard-data/UnknownPluginData.json/")
    )
    assert entry.source_type == "nonstandard_data"
    assert entry.rule_source == "非标准 data 文件文本规则"
    assert entry.original_lines == ["これは無視される"]
    assert entry.enters_translation is True
    item = next(
        item
        for data in scope.translation_data_map.values()
        for item in data.translation_items
        if item.location_path == entry.location_path
    )
    assert item.fact_id
    assert item.source_fact_raw_hash
    assert item.source_fact_translatable_hash


@pytest.mark.asyncio
async def test_nonstandard_data_text_scope_uses_native_leaves_for_imported_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """统一文本清单处理已导入非标准 data 规则。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                }
            ],
            ensure_ascii=False,
        ),
    )
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)

    async with await registry.open_game("テストゲーム") as session:
        scope = await rebuild_current_text_fact_scope_for_test(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )

    entry = next(
        item
        for item in scope.entries
        if item.location_path.startswith("nonstandard-data/UnknownPluginData.json/")
    )
    assert entry.original_lines == ["これは無視される"]
    assert entry.enters_translation is True


@pytest.mark.asyncio
async def test_nonstandard_data_write_back_updates_managed_json_leaf(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """写回只替换非标准 data 规则命中的 JSON 字符串叶子。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                }
            ],
            ensure_ascii=False,
        ),
    )
    game_data = await load_translation_source_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        records = await session.read_nonstandard_data_text_rules()
    location_path = "nonstandard-data/UnknownPluginData.json/$[0]['name']"
    items = [
        TranslationItem(
            location_path=location_path,
            item_type="short_text",
            original_lines=["これは無視される"],
            source_line_paths=[location_path],
            translation_lines=["非标准译文"],
        )
    ]

    write_data_text(game_data, items, nonstandard_data_rule_records=records)

    written_raw = cast(
        object,
        json.loads((minimal_game_dir / "data" / "UnknownPluginData.json").read_text(encoding="utf-8")),
    )
    written_value = ensure_json_array(coerce_json_value(written_raw), "UnknownPluginData.json")
    assert written_value == [{"id": 1, "name": "非标准译文"}]


@pytest.mark.asyncio
async def test_active_runtime_audit_reports_nonstandard_data_source_residual(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行审计会检查已管理非标准 data 路径中的源文残留。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                }
            ],
            ensure_ascii=False,
        ),
    )

    report = await service.audit_active_runtime(game_title="テストゲーム")

    assert report.status == "error"
    assert "active_runtime_nonstandard_data_source_residual" in {error.code for error in report.errors}
    assert report.summary["active_runtime_nonstandard_data_managed_path_count"] == 1
    assert report.summary["active_runtime_nonstandard_data_source_residual_count"] == 1
    assert report.details["active_runtime_nonstandard_data_items"]


@pytest.mark.asyncio
async def test_active_runtime_audit_uses_native_nonstandard_data_leaves(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行审计处理已管理非标准 data 路径。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await service.import_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                }
            ],
            ensure_ascii=False,
        ),
    )
    report = await service.audit_active_runtime(game_title="テストゲーム")

    assert "active_runtime_nonstandard_data_source_residual" in {error.code for error in report.errors}
    assert report.summary["active_runtime_nonstandard_data_managed_path_count"] == 1


@pytest.mark.asyncio
async def test_nonstandard_data_rules_reject_skipped_with_paths(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """`skipped=true` 不能同时携带翻译路径。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_nonstandard_data_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$[*]['name']"],
                    "excluded_paths": [],
                    "skipped": True,
                }
            ],
            ensure_ascii=False,
        ),
    )

    assert report.status == "error"
    assert "skipped=true" in report.errors[0].message


def test_nonstandard_data_rules_reject_dot_jsonpath() -> None:
    """路径模板沿用受限括号 JSONPath，不接受点号路径。"""
    with pytest.raises(ValueError, match="JSONPath 超出当前规则范围"):
        _ = parse_nonstandard_data_rule_import_text(
            json.dumps(
                [
                    {
                        "file": "Recipes.json",
                        "paths": ["$.Name"],
                        "excluded_paths": [],
                    }
                ],
                ensure_ascii=False,
            )
        )


def test_nonstandard_data_rule_import_normalizes_integer_file_before_business_validation() -> None:
    """非标准 data 规则导入中的整数 file 按文本字段规范化后再执行业务校验。"""
    with pytest.raises(ValueError, match="file 必须是 JSON 文件名"):
        _ = parse_nonstandard_data_rule_import_text(
            json.dumps(
                [
                    {
                        "file": 123,
                        "paths": [],
                        "excluded_paths": [],
                    }
                ],
                ensure_ascii=False,
            )
        )


def test_nonstandard_data_rule_import_normalizes_integer_path_before_business_validation() -> None:
    """非标准 data 规则导入中的整数路径按文本字段规范化后再执行业务校验。"""
    with pytest.raises(ValueError, match="JSONPath"):
        _ = parse_nonstandard_data_rule_import_text(
            json.dumps(
                [
                    {
                        "file": "Recipes.json",
                        "paths": [123],
                        "excluded_paths": [],
                    }
                ],
                ensure_ascii=False,
            )
        )


def test_nonstandard_data_rule_import_rejects_boolean_path() -> None:
    """非标准 data 规则导入中的布尔路径无效。"""
    with pytest.raises(Exception) as error_info:
        _ = parse_nonstandard_data_rule_import_text(
            json.dumps(
                [
                    {
                        "file": "Recipes.json",
                        "paths": [True],
                    }
                ],
                ensure_ascii=False,
            )
        )

    assert "bool" in str(error_info.value)


@pytest.mark.parametrize("skipped_value", [1, "true"])
def test_nonstandard_data_rule_import_requires_boolean_skipped(skipped_value: object) -> None:
    """非标准 data 规则导入中的 skipped 只接受真实布尔值。"""
    with pytest.raises(Exception):
        _ = parse_nonstandard_data_rule_import_text(
            json.dumps(
                [
                    {
                        "file": "Recipes.json",
                        "paths": [],
                        "excluded_paths": [],
                        "skipped": skipped_value,
                    }
                ],
                ensure_ascii=False,
            )
        )
