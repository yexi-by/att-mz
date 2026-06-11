from app.native_rule_runtime import prepare_rule_import


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
