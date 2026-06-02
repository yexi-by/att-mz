"""非标准 data 文件文本扫描、导出和规则校验测试。"""

import json
from pathlib import Path
from typing import cast

import pytest

from app.agent_toolkit import AgentToolkitService
from app.application.flow_gate import collect_workflow_gate_errors
from app.nonstandard_data import (
    build_nonstandard_data_scan,
    build_nonstandard_data_file_hash,
    NonstandardDataRuleImportFile,
    NonstandardDataRuleValidationResult,
    NonstandardDataScan,
    NonstandardDataTextExtraction,
    parse_nonstandard_data_rule_import_text,
    validate_nonstandard_data_rules,
)
from app.persistence import GameRegistry
from app.rmmz.game_file_view import GameFileView
from app.rmmz.json_types import coerce_json_value, ensure_json_array, ensure_json_object
from app.rmmz.loader import load_translation_source_game_data, resolve_game_layout
from app.rmmz.schema import NonstandardDataTextRuleRecord
from app.rmmz.text_rules import TextRules
from app.text_scope import TextScopeService
from app.utils.config_loader_utils import load_setting
from tests._native_write_plan_helper import write_data_text
from tests.conftest import EXAMPLE_SETTING_PATH, write_json


def _write_high_risk_nonstandard_data(game_root: Path) -> None:
    """写入测试用高风险非标准 data 文件。"""
    write_json(game_root / "data" / "UnknownPluginData.json", [{"id": 1, "name": "これは無視される"}])


@pytest.mark.asyncio
async def test_nonstandard_data_scan_reports_high_risk_candidates(minimal_game_dir: Path) -> None:
    """扫描只把非标准 data JSON 中的源语言自然文本列为候选。"""
    _write_high_risk_nonstandard_data(minimal_game_dir)
    layout = resolve_game_layout(minimal_game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)

    scan = await build_nonstandard_data_scan(
        layout=layout,
        source_view=GameFileView.ACTIVE_RUNTIME,
        text_rules=text_rules,
    )

    assert scan.high_risk
    assert [candidate.json_path for candidate in scan.candidates] == ["$[0]['name']"]
    assert scan.candidates[0].file_name == "UnknownPluginData.json"
    assert scan.candidates[0].source_text == "これは無視される"


@pytest.mark.asyncio
async def test_nonstandard_data_scan_respects_english_protocol_noise(
    minimal_english_game_dir: Path,
) -> None:
    """英文项目不会把资源名、公式和协议值误报为高风险。"""
    data_dir = minimal_english_game_dir / "data"
    write_json(
        data_dir / "Recipes.json",
        [
            {
                "id": "recipe_001",
                "icon": "img/pictures/Meal.png",
                "enabled": "true",
                "formula": "a.hpRate() >= 0.5",
            }
        ],
    )
    layout = resolve_game_layout(minimal_english_game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="en")
    text_rules = TextRules.from_setting(setting.text_rules)

    scan = await build_nonstandard_data_scan(
        layout=layout,
        source_view=GameFileView.ACTIVE_RUNTIME,
        text_rules=text_rules,
    )

    assert not scan.high_risk
    assert scan.summary_json()["nonstandard_file_count"] == 1
    assert scan.summary_json()["candidate_count"] == 0


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
async def test_nonstandard_data_rules_validate_full_classification(
    minimal_game_dir: Path,
) -> None:
    """规则必须把全部源语言自然文本候选归入翻译或排除。"""
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

    validation = validate_nonstandard_data_rules(scan=scan, import_file=import_file)

    assert validation.rule_count == 1
    assert validation.reviewed_candidate_count == 1
    assert validation.unreviewed_candidate_paths == ()


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
        before_errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
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
        after_errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
        )

    assert "nonstandard_data_high_risk" in {error.code for error in before_errors}
    assert import_report.status == "ok"
    assert "nonstandard_data_high_risk" not in {error.code for error in after_errors}


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
        await session.replace_nonstandard_data_text_rules(
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
    game_data = await load_translation_source_game_data(minimal_game_dir)

    async with await registry.open_game("テストゲーム") as session:
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
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
    items = NonstandardDataTextExtraction(game_data, records).extract_all_text()[
        "nonstandard-data/UnknownPluginData.json"
    ].translation_items
    items[0].translation_lines = ["非标准译文"]

    write_data_text(game_data, items)

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
