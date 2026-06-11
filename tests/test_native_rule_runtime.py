from pathlib import Path
import sqlite3

import pytest

from app.native_rule_runtime import (
    build_rules_fingerprint,
    commit_rule_import,
    evaluate_runtime_config_patterns,
    prepare_rule_import,
)
from app.persistence.sql import current_schema_sql
from app.rmmz.json_types import JsonObject, JsonValue, ensure_json_array, ensure_json_object


def _valid_runtime_patterns() -> JsonObject:
    return {
        "source_text_required_pattern": r"[ぁ-んァ-ヶ一-龯ー]+",
        "source_residual_segment_pattern": r"[ぁ-んァ-ヶー]+",
        "line_width_count_pattern": r"\S",
        "residual_escape_sequence_pattern": r"\\[nrt]",
    }


def test_prepare_rule_import_rejects_unknown_domain() -> None:
    payload: JsonObject = {
        "mode": "validate",
        "domain": "unknown_domain",
        "rules_payload": {},
        "game_context": {},
        "settings_runtime_patterns": _valid_runtime_patterns(),
    }
    result = prepare_rule_import(payload)

    assert result.status == "error"
    assert result.errors[0].code == "rule_domain_invalid"


def test_prepare_rejects_invalid_config_pcre2_pattern() -> None:
    settings_runtime_patterns = _valid_runtime_patterns()
    settings_runtime_patterns["source_text_required_pattern"] = "(?<bad"
    payload: JsonObject = {
        "mode": "validate",
        "domain": "placeholders",
        "rules_payload": {},
        "game_context": {},
        "settings_runtime_patterns": settings_runtime_patterns,
    }
    result = prepare_rule_import(payload)

    assert result.status == "error"
    assert result.errors[0].code == "pcre2_compile_error"
    assert result.errors[0].field == "source_text_required_pattern"


def test_evaluate_runtime_config_patterns_uses_current_pcre2_pattern() -> None:
    payload: JsonObject = {
        "settings_runtime_patterns": _valid_runtime_patterns(),
        "texts": [
            {"id": "ja", "text": "こんにちは"},
            {"id": "en", "text": "Inventory"},
        ],
    }
    result = evaluate_runtime_config_patterns(payload)

    assert result.status == "ok"
    assert [entry.source_text_required for entry in result.entries] == [True, False]
    assert [entry.line_width_count for entry in result.entries] == [5, 9]


@pytest.mark.parametrize(
    ("domain", "payload", "matcher_kind"),
    [
        (
            "plugin_config",
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Message']"],
                }
            ],
            "json_path_template",
        ),
        (
            "event_commands",
            {"357": [{"match": {"0": "Speaker"}, "paths": ["$['parameters'][1]['message']"]}]},
            "json_path_template",
        ),
        ("note_tags", {"Actors.json": ["profile"]}, "literal"),
        (
            "nonstandard_data",
            {"Data.json": ["$['items'][*]['description']"]},
            "json_path_template",
        ),
        (
            "plugin_source",
            {
                "rules": [
                    {
                        "file": "Foo.js",
                        "selectors": ["string@0:4"],
                        "excluded_selectors": [],
                    }
                ]
            },
            "ast_selector",
        ),
    ],
)
def test_prepare_non_regex_domains_do_not_require_pcre2(
    domain: str,
    payload: JsonValue,
    matcher_kind: str,
) -> None:
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": domain,
            "rules_payload": payload,
            "game_context": {"allow_empty_context_for_contract_test": True},
            "settings_runtime_patterns": _valid_runtime_patterns(),
        }
    )

    assert result.status == "ok"
    runtime_summary = ensure_json_object(result.summary["rule_runtime"], "rule_runtime")
    matcher_kinds = ensure_json_array(runtime_summary["matcher_kinds"], "rule_runtime.matcher_kinds")
    assert matcher_kinds[0] == matcher_kind


def test_validate_prepare_returns_plan_without_db_write(tmp_path: Path) -> None:
    db_path = _temp_game_db_path(tmp_path)
    payload: JsonObject = {
        "mode": "validate",
        "db_path": str(db_path),
        "domain": "placeholders",
        "rules_payload": {},
        "game_context": {},
        "settings_runtime_patterns": _valid_runtime_patterns(),
    }
    result = prepare_rule_import(payload)

    assert result.status == "ok"
    assert result.plan_token is not None
    assert result.plan_token.startswith("plan:")
    assert result.prepared_plan is not None
    assert result.prepared_plan["domain"] == "placeholders"
    assert result.summary["mode"] == "validate"
    assert not db_path.exists()


def test_prepare_and_commit_report_real_stage_diagnostics(tmp_path: Path) -> None:
    db_path = _temp_game_db_path(tmp_path)
    with sqlite3.connect(db_path) as connection:
        _ = connection.executescript(current_schema_sql())
    prepare_result = prepare_rule_import(
        {
            "mode": "import",
            "db_path": str(db_path),
            "domain": "placeholders",
            "rules_payload": {r"\\V\[(?<index>\d+)\]": "[CUSTOM_VAR_{index}]"},
            "game_context": {"scope_hash": "diagnostics"},
            "settings_runtime_patterns": _valid_runtime_patterns(),
        }
    )

    assert prepare_result.status == "ok"
    prepare_runtime = _rule_runtime_diagnostics(prepare_result.details)
    assert isinstance(prepare_runtime["compile_ms"], int)
    assert "store_ms" not in prepare_runtime
    assert prepare_result.plan_token is not None
    assert prepare_result.prepared_plan is not None
    commit_result = commit_rule_import(
        {
            "db_path": str(db_path),
            "domain": "placeholders",
            "plan_token": prepare_result.plan_token,
            "prepared_plan": prepare_result.prepared_plan,
            "backup_path": None,
        }
    )

    assert commit_result.status == "ok"
    commit_runtime = _rule_runtime_diagnostics(commit_result.details)
    assert isinstance(commit_runtime["store_ms"], int)
    assert "compile_ms" not in commit_runtime
    assert isinstance(commit_runtime["thread_count"], int)
    assert commit_runtime["thread_count"] > 0
    assert isinstance(commit_runtime["jit_enabled"], bool)


def test_import_commit_rejects_mismatched_plan_token(tmp_path: Path) -> None:
    prepare_result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "placeholders",
            "rules_payload": {},
            "game_context": {},
            "settings_runtime_patterns": _valid_runtime_patterns(),
        }
    )

    assert prepare_result.prepared_plan is not None
    result = commit_rule_import(
        {
            "db_path": str(_temp_game_db_path(tmp_path)),
            "domain": "placeholders",
            "plan_token": "wrong-token",
            "prepared_plan": prepare_result.prepared_plan,
            "backup_path": None,
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "rule_import_plan_stale"


def test_build_rules_fingerprint_reads_unified_rule_store(tmp_path: Path) -> None:
    db_path = _temp_game_db_path(tmp_path)
    connection = sqlite3.connect(db_path)
    _ = connection.executescript(current_schema_sql())
    before = build_rules_fingerprint(
        {
            "db_path": str(db_path),
            "settings_runtime_patterns": _valid_runtime_patterns(),
        }
    )
    _ = connection.execute(
        """
        INSERT INTO rules(rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash)
        VALUES ('rule:test', 'placeholders', 0, 'pcre2_pattern', '\\\\V\\[(?<index>\\d+)\\]', '{"placeholder_template":"[CUSTOM_VAR_{index}]"}', 1, 'external_import', 'hash:test')
        """
    )
    connection.commit()
    after = build_rules_fingerprint(
        {
            "db_path": str(db_path),
            "settings_runtime_patterns": _valid_runtime_patterns(),
        }
    )

    assert before != after
    assert len(before) == 64
    assert len(after) == 64


def _temp_game_db_path(tmp_path: Path) -> Path:
    return tmp_path / "game.db"


def _rule_runtime_diagnostics(details: JsonObject) -> JsonObject:
    diagnostics = ensure_json_object(details["diagnostics"], "diagnostics")
    return ensure_json_object(diagnostics["rule_runtime"], "diagnostics.rule_runtime")
