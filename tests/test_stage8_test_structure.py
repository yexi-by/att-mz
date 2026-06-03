"""阶段 8 测试体系结构约束。"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

AGENT_TOOLKIT_DOMAIN_TESTS = (
    "test_agent_toolkit_workspace.py",
    "test_agent_toolkit_rule_import.py",
    "test_agent_toolkit_workflow_gate.py",
    "test_agent_toolkit_manual_import.py",
    "test_agent_toolkit_quality_report.py",
    "test_agent_toolkit_feedback.py",
    "test_agent_toolkit_coverage.py",
    "test_agent_toolkit_translation_limits.py",
)

RMMZ_WRITEBACK_DOMAIN_TESTS = (
    "test_rmmz_source_snapshot.py",
    "test_rmmz_write_plan.py",
    "test_rmmz_file_transaction.py",
    "test_rmmz_font_transaction.py",
    "test_rmmz_post_write_audit.py",
    "test_rmmz_mv_namebox.py",
    "test_rmmz_note_nonstandard_data.py",
)

LEGACY_MONOLITH_TESTS = (
    "test_agent_toolkit.py",
    "test_rmmz_loader_extraction_writeback.py",
)


def test_stage8_domain_test_files_replace_legacy_monoliths() -> None:
    """大文件测试必须拆成业务契约文件，不再承载测试函数。"""
    missing_domain_files = [
        file_name
        for file_name in (*AGENT_TOOLKIT_DOMAIN_TESTS, *RMMZ_WRITEBACK_DOMAIN_TESTS)
        if not (TESTS_DIR / file_name).is_file()
    ]
    assert missing_domain_files == []

    legacy_test_functions: dict[str, list[str]] = {}
    for file_name in LEGACY_MONOLITH_TESTS:
        path = TESTS_DIR / file_name
        if not path.exists():
            continue
        parsed = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = [
            node.name
            for node in parsed.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_")
        ]
        if names:
            legacy_test_functions[file_name] = names

    assert legacy_test_functions == {}
