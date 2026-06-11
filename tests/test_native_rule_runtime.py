from pathlib import Path

import pytest

from app.native_rule_runtime import (
    commit_rule_import,
    evaluate_runtime_config_patterns,
    prepare_rule_import,
)
from app.rmmz.json_types import JsonObject, JsonValue, ensure_json_array, ensure_json_object


def _valid_runtime_patterns() -> JsonObject:
    return {
        "source_text_required_pattern": r"[\p{Hiragana}\p{Katakana}\p{Han}ー]+",
        "source_residual_segment_pattern": r"[\p{Hiragana}\p{Katakana}ー]+",
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
    assert result.summary["mode"] == "validate"
    assert not db_path.exists()


def test_import_commit_rejects_mismatched_plan_token(tmp_path: Path) -> None:
    result = commit_rule_import(
        {
            "db_path": str(_temp_game_db_path(tmp_path)),
            "domain": "placeholders",
            "plan_token": "wrong-token",
            "backup_path": None,
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "rule_import_plan_stale"


def _temp_game_db_path(tmp_path: Path) -> Path:
    return tmp_path / "game.db"
