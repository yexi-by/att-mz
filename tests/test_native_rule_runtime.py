from pathlib import Path

from app.native_rule_runtime import commit_rule_import, prepare_rule_import


def test_prepare_rule_import_rejects_unknown_domain() -> None:
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "unknown_domain",
            "rules_payload": {},
            "game_context": {},
            "settings_runtime_patterns": {},
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "rule_domain_invalid"


def test_validate_prepare_returns_plan_without_db_write(tmp_path: Path) -> None:
    db_path = _temp_game_db_path(tmp_path)
    result = prepare_rule_import(
        {
            "mode": "validate",
            "db_path": str(db_path),
            "domain": "placeholders",
            "rules_payload": {},
            "game_context": {},
            "settings_runtime_patterns": {},
        }
    )

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
