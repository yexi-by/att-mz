"""Rust Scope/Index Engine 当前扫描预算和旧路径边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path

from app.json_path_protocol import (
    jsonpath_to_event_command_location_path,
    jsonpath_to_plugin_location_path,
)
from tests import scan_budget_contract
from tests.scan_budget_contract import (
    P0_COMMANDS,
    P1_A_COMMANDS,
    P1_B_COMMANDS,
    P1_B_PENDING_FACT_SOURCE_COMMANDS,
    P1_C_COMMANDS,
    required_scan_budget_commands_by_category,
    scan_budget_for_command,
    scan_budgets_by_command,
)


def _source_for_function(source: str, function_name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == function_name:
            segment = ast.get_source_segment(source, node)
            if segment is None:
                raise AssertionError(f"无法定位函数源码: {function_name}")
            return segment
    raise AssertionError(f"缺少函数: {function_name}")


def _call_names_for_function(source: str, function_name: str) -> set[str]:
    function_source = _source_for_function(source, function_name)
    tree = ast.parse(function_source)
    call_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            call_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            call_names.add(node.func.attr)
    return call_names


def _exported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "__all__":
            value_node = node.value
        if not isinstance(value_node, ast.Tuple | ast.List):
            continue
        return {
            item.value
            for item in value_node.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
    return set()


def _python_paths_containing(
    marker: str,
    *,
    roots: tuple[Path, ...] | None = None,
    excluded_paths: set[str] | None = None,
) -> set[str]:
    roots = roots or (Path("app"), Path("tests"))
    excluded_paths = excluded_paths or set()
    paths: set[str] = set()
    for path in roots:
        for candidate in path.rglob("*.py"):
            candidate_text_path = candidate.as_posix()
            if candidate_text_path in excluded_paths:
                continue
            if marker in candidate.read_text(encoding="utf-8"):
                paths.add(candidate_text_path)
    return paths


def test_json_path_protocol_is_neutral_between_plugin_and_event_domains() -> None:
    """插件和事件指令共享中性 JSON path 协议。"""
    assert jsonpath_to_plugin_location_path(
        json_path="$['parameters']['title']",
        plugin_index=3,
    ) == "plugins.js/3/title"
    assert jsonpath_to_event_command_location_path(
        json_path="$['parameters'][2]",
        command_location_path="CommonEvents.json/1/4",
    ) == "CommonEvents.json/1/4/parameters/2"

    event_sources = [
        Path("app/event_command_text/extraction.py").read_text(encoding="utf-8"),
        Path("app/event_command_text/importer.py").read_text(encoding="utf-8"),
        Path("app/text_scope/rule_hits.py").read_text(encoding="utf-8"),
    ]
    assert all("app.plugin_text.paths" not in source for source in event_sources)


def test_rust_scope_index_scan_budget_table_covers_current_p0_p1_commands() -> None:
    """预算总表必须覆盖当前 P0/P1 命令，并限制每类重型动作次数。"""
    budgets = scan_budgets_by_command()
    required_by_category = required_scan_budget_commands_by_category()
    required_commands: set[str] = set()
    for commands in required_by_category.values():
        required_commands.update(commands)

    assert set(budgets) == required_commands
    assert len(P0_COMMANDS) == 1
    assert len(P1_A_COMMANDS) == 13
    assert len(P1_B_COMMANDS) == 30
    assert len(P1_C_COMMANDS) == 7
    assert P1_B_PENDING_FACT_SOURCE_COMMANDS == frozenset()

    for command_name, budget in budgets.items():
        max_game_data_load_count = 2 if command_name == "diagnose-active-runtime" else 1
        assert budget.game_data_load_count <= max_game_data_load_count, command_name
        assert budget.text_scope_build_count <= 1, command_name
        assert budget.candidate_scan_count <= 1, command_name
        assert budget.plugin_source_ast_scan_count <= 1, command_name
        assert budget.quality_gate_count <= 1, command_name
        assert budget.write_plan_count <= 1, command_name
        assert budget.authoritative_source.strip(), command_name
        assert budget.old_path_action.strip(), command_name
        assert budget.evidence.strip(), command_name

    for category, commands in required_by_category.items():
        assert commands == {
            command_name
            for command_name, budget in budgets.items()
            if budget.category == category
        }


def test_budget_facts_keep_single_authoritative_native_or_sqlite_source() -> None:
    """关键命令的事实来源必须落在 Rust/native/SQLite 当前路径。"""
    expected_sources = {
        "export-pending-translations --limit": "SQLite text_index_items pending 快路径",
        "rebuild-text-index": "Rust build_scope_index / SQLite text index",
        "quality-report": "Rust evaluate_scope_gate / Rust quality / SQLite text index",
        "write-back": "Rust evaluate_scope_gate / Rust write plan",
        "prepare-agent-workspace": "Rust build_scope_index / scan_rule_candidates",
        "scan-plugin-source-text": "Rust scan_rule_candidates(plugin_source)",
        "scan-nonstandard-data": "Rust scan_rule_candidates(nonstandard_data)",
        "scan-placeholder-candidates": "Rust scan_rule_candidates(placeholders)",
        "scan-structured-placeholder-candidates": "Rust scan_rule_candidates(structured_placeholders)",
        "export-note-tag-candidates": "Rust scan_rule_candidates(note_tags)",
        "export-event-commands-json": "Rust scan_rule_candidates(event_commands)",
        "validate-plugin-rules": "Rust scan_rule_candidates(plugin_config)",
        "export-mv-virtual-namebox-candidates": "Rust scan_rule_candidates(mv_virtual_namebox)",
        "validate-source-residual-rules": "SQLite text_index_items",
        "verify-feedback-text": "SQLite text_index_items / Rust plugin source runtime scan",
        "export-terminology": "terminology repository / terminology context",
        "probe-source-language": "raw JSON visible-text sampler",
        "export-plugins-json": "plugins.js parser / plugin config reader",
    }

    for command_name, expected_source in expected_sources.items():
        budget = scan_budget_for_command(command_name)
        assert expected_source in budget.authoritative_source
        for text in (budget.authoritative_source, budget.old_path_action, budget.evidence):
            assert "待复核:" not in text
            assert "目标 Rust scan_rule_candidates" not in text


def test_p1b_candidate_commands_are_closed_over_native_or_sqlite_boundaries() -> None:
    """P1-B 规则支线不再保留待复核事实来源集合。"""
    budgets = scan_budgets_by_command()
    p1b_budgets = {
        command_name: budget
        for command_name, budget in budgets.items()
        if budget.category == "P1-B"
    }

    assert set(p1b_budgets) == set(P1_B_COMMANDS)
    assert set(scan_budget_contract.P1_B_PENDING_FACT_SOURCE_COMMANDS) == set()

    source_residual_commands = {"validate-source-residual-rules", "import-source-residual-rules"}
    for command_name, budget in p1b_budgets.items():
        if command_name in source_residual_commands:
            assert budget.candidate_scan_count == 0
            assert "SQLite text_index_items" in budget.authoritative_source
        else:
            assert budget.candidate_scan_count == 1
            assert "scan_rule_candidates" in budget.authoritative_source
        assert budget.quality_gate_count == 0
        assert budget.write_plan_count == 0


def test_legacy_plugin_source_scanner_helpers_are_not_public_or_production_paths() -> None:
    """旧插件源码全量 scanner helper 不能作为公共导出或生产默认路径残留。"""
    package_exports = _exported_names(Path("app/plugin_source_text/__init__.py"))
    scanner_source = Path("app/plugin_source_text/scanner.py").read_text(encoding="utf-8")
    native_source = Path("app/plugin_source_text/native_scan.py").read_text(encoding="utf-8")
    scanner_exports = _exported_names(Path("app/plugin_source_text/scanner.py"))

    assert "build_native_plugin_source_scan" in package_exports
    assert "scan_plugin_source_runtime_files_text_strict" not in package_exports
    assert "scan_plugin_source_runtime_files_text_strict" in scanner_exports
    assert "scan_plugin_source_files_text_strict" not in package_exports
    assert "scan_plugin_source_file_text" not in scanner_exports
    assert "scan_plugin_source_file_text_strict" not in scanner_exports
    assert "find_candidate_by_selector" not in scanner_exports

    legacy_markers = (
        "_build_legacy_plugin_source_scan",
        "_scan_legacy_plugin_source_files_text_strict",
    )
    for marker in legacy_markers:
        assert marker not in scanner_source
        assert _python_paths_containing(marker, roots=(Path("app"),)) == set()

    native_entrypoints = {
        "build_native_plugin_source_risk_report": "build_native_plugin_source_risk_report_from_inputs",
        "build_native_plugin_source_ast_map_payload": "build_native_plugin_source_ast_map_payload_from_inputs",
        "build_native_plugin_source_scan": "",
    }
    for function_name, delegated_function_name in native_entrypoints.items():
        call_names = _call_names_for_function(native_source, function_name)
        if "scan_native_rule_candidates" in call_names:
            continue
        assert delegated_function_name
        assert delegated_function_name in call_names
        delegated_call_names = _call_names_for_function(native_source, delegated_function_name)
        if "scan_native_rule_candidates" in delegated_call_names:
            continue
        assert "build_native_plugin_source_ast_map_payload_and_risk_report_from_inputs" in delegated_call_names
        assert "scan_native_rule_candidates" in _call_names_for_function(
            native_source,
            "build_native_plugin_source_ast_map_payload_and_risk_report_from_inputs",
        )


def test_nonstandard_data_scanner_helpers_are_not_package_root_exports() -> None:
    """非标准 data 低层 scanner 只从 scanner 模块显式使用。"""
    package_exports = _exported_names(Path("app/nonstandard_data/__init__.py"))
    scanner_exports = _exported_names(Path("app/nonstandard_data/scanner.py"))

    scanner_api = {
        "NONSTANDARD_DATA_SOURCE_TYPE",
        "NonstandardDataCandidate",
        "NonstandardDataFile",
        "NonstandardDataFileScan",
        "NonstandardDataScan",
        "build_nonstandard_data_candidates_payload",
        "build_nonstandard_data_file_hash",
        "build_nonstandard_data_scan",
        "export_nonstandard_data_workspace",
        "load_nonstandard_data_files",
        "resolve_nonstandard_data_file_leaves_native",
    }

    assert scanner_api <= scanner_exports
    assert package_exports.isdisjoint(scanner_api)
    assert "validate_nonstandard_data_rules" in package_exports
    assert "NonstandardDataTextExtraction" in package_exports


def test_current_runtime_and_p1c_commands_do_not_rebuild_text_scope_by_default() -> None:
    """P1-C 保留真实 I/O 成本，但不回退到 TextScopeService 或旧源码候选扫描。"""
    feedback_source = Path("app/agent_toolkit/services/feedback.py").read_text(encoding="utf-8")
    common_source = Path("app/agent_toolkit/services/common.py").read_text(encoding="utf-8")
    quality_source = Path("app/agent_toolkit/services/quality.py").read_text(encoding="utf-8")
    handler_source = Path("app/application/handler.py").read_text(encoding="utf-8")
    probe_source = Path("app/source_language_probe.py").read_text(encoding="utf-8")

    verify_source = _source_for_function(feedback_source, "verify_feedback_text")
    assert "TextScopeService" not in verify_source
    assert "text_index_items_to_scope" not in verify_source

    collect_calls = _call_names_for_function(common_source, "_collect_feedback_text_occurrences")
    assert "scan_plugin_source_runtime_files_text_strict" in collect_calls
    assert "_collect_plugin_source_text_candidates" not in collect_calls
    assert "PLUGIN_SOURCE_TEXT_PATTERN" not in common_source

    for function_name in ("audit_active_runtime", "diagnose_active_runtime"):
        runtime_source = _source_for_function(quality_source, function_name)
        runtime_calls = _call_names_for_function(quality_source, function_name)
        assert "audit_active_runtime_plugin_source_with_scan_cache" in runtime_calls
        assert "TextScopeService" not in runtime_source

    export_calls = _call_names_for_function(handler_source, "export_terminology")
    import_source = _source_for_function(handler_source, "import_terminology")
    import_calls = _call_names_for_function(handler_source, "import_terminology")
    assert "_load_session_game_data" in export_calls
    assert "export_terminology_artifacts" in export_calls
    assert "extract_registry" in import_calls
    assert "extract_registry_and_contexts" not in import_calls
    assert "TextScopeService" not in import_source

    language_probe = _source_for_function(probe_source, "probe_source_language")
    language_probe_calls = _call_names_for_function(probe_source, "probe_source_language")
    assert "_read_standard_json_files" in language_probe_calls
    assert "_collect_visible_texts" in language_probe_calls
    assert "load_game_data" not in language_probe_calls
    assert "TextScopeService" not in language_probe


def test_agent_toolkit_scope_map_helper_uses_rust_text_index_not_python_scope_build() -> None:
    """Agent 小命令读取正文事实时不能回退到 Python 完整文本范围构建。"""
    core_source = Path("app/agent_toolkit/services/core.py").read_text(encoding="utf-8")

    extract_source = _source_for_function(core_source, "_extract_active_translation_data_map")
    read_index_source = _source_for_function(core_source, "_read_active_translation_data_map_from_text_index")
    read_index_calls = _call_names_for_function(core_source, "_read_active_translation_data_map_from_text_index")

    assert "TextScopeService" not in extract_source
    assert "TextScopeService" not in read_index_source
    assert "rebuild_text_index_native_storage" in read_index_calls
    assert "text_index_items_to_translation_data_map" in read_index_calls


def test_batch7_production_paths_do_not_keep_python_text_scope_fallbacks() -> None:
    """批次 7 后核心生产路径不得保留旧 Python 完整文本范围回退入口。"""
    production_paths = (
        Path("app/application/handler.py"),
        Path("app/application/flow_gate.py"),
        Path("app/application/write_back_gate.py"),
        Path("app/agent_toolkit/services/coverage.py"),
        Path("app/agent_toolkit/services/quality.py"),
        Path("app/agent_toolkit/services/text_index.py"),
        Path("app/text_index.py"),
    )
    for path in production_paths:
        source = path.read_text(encoding="utf-8")
        assert "TextScopeService" not in source, path.as_posix()

    text_index_source = Path("app/text_index.py").read_text(encoding="utf-8")
    text_index_service_source = Path("app/agent_toolkit/services/text_index.py").read_text(encoding="utf-8")
    text_index_exports = _exported_names(Path("app/text_index.py"))
    assert "async def rebuild_text_index(" not in text_index_source
    assert "rebuild_text_index" not in text_index_exports
    assert "TextScopeService" not in _source_for_function(text_index_service_source, "rebuild_text_index")
    assert "text_index_items_to_scope" not in _source_for_function(
        text_index_service_source,
        "rebuild_text_index",
    )
    assert "build_text_index_workflow_gate_scope_hashes" not in text_index_source
    assert "build_text_index_workflow_gate_scope_hashes" not in text_index_exports
    for old_bridge_marker in (
        "_scope_index_payload_from_scope",
        "_text_index_records_from_native_rows",
        "_scope_summary_record_from_native",
        "_domain_summary_records_from_native",
        "_rule_hit_summary_records_from_native",
    ):
        assert old_bridge_marker not in text_index_source


def test_task9_agent_common_does_not_reconstruct_scope_from_v1_index_rows() -> None:
    """Agent 公共层不能再把 v1 text_index_items 还原成旧 TextScopeResult。"""
    common_source = Path("app/agent_toolkit/services/common.py").read_text(encoding="utf-8")
    common_exports = _exported_names(Path("app/agent_toolkit/services/common.py"))

    for old_scope_marker in (
        "text_index_records_to_scope",
        "build_text_index_text_scope_report",
        "_text_scope_blocking_errors",
    ):
        assert old_scope_marker not in common_source
        assert old_scope_marker not in common_exports

    for old_model_marker in (
        "TextScopeResult(",
        "TextScopeEntry(",
        "TranslationData(display_name=None, translation_items=[])",
    ):
        assert old_model_marker not in common_source


def test_workspace_mv_namebox_and_plugin_export_use_current_thin_adapters() -> None:
    """工作区、MV 虚拟名字框和插件配置导出保持薄适配当前边界。"""
    workspace_source = Path("app/agent_toolkit/services/workspace.py").read_text(encoding="utf-8")
    mv_native_source = Path("app/rmmz/mv_namebox_native.py").read_text(encoding="utf-8")
    handler_source = Path("app/application/handler.py").read_text(encoding="utf-8")
    exporter_source = Path("app/plugin_text/exporter.py").read_text(encoding="utf-8")

    workspace_index_calls = _call_names_for_function(
        workspace_source,
        "_read_workspace_placeholder_entries_from_text_index",
    )
    assert "detect_text_index_invalidations" in workspace_index_calls
    assert "rebuild_text_index_native_storage" in workspace_index_calls
    assert "rebuild_persistent_text_index" not in workspace_source
    assert "read_text_index_placeholder_texts" not in workspace_source
    assert "read_current_text_fact_placeholder_entries_v2" in workspace_index_calls
    assert "text_index_items_to_translation_data_map" not in workspace_source

    assert "scan_native_rule_candidates" in _call_names_for_function(mv_native_source, "scan_native_mv_virtual_namebox")
    assert "collect_mv_virtual_namebox_candidates" not in mv_native_source

    export_plugins_source = _source_for_function(handler_source, "export_plugins_json")
    export_plugins_calls = _call_names_for_function(handler_source, "export_plugins_json")
    assert "_load_session_game_data" in export_plugins_calls
    assert "export_plugins_json_file" in export_plugins_calls
    for marker in (
        "TextScopeService",
        "scan_plugin_source_runtime_files_text_strict",
        "build_native_plugin_source_scan",
        "detect_text_index_invalidations",
    ):
        assert marker not in export_plugins_source
        assert marker not in exporter_source
