from pathlib import Path

from app.native_rule_runtime import commit_rule_import, prepare_rule_import
from app.rmmz.json_types import JsonObject


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
