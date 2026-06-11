from pathlib import Path
from typing import cast

import pytest

from app.native_rule_runtime import prepare_rule_import
from app.persistence import GameRegistry
from app.rmmz.json_types import JsonObject, coerce_json_value, ensure_json_object


def _valid_runtime_patterns() -> JsonObject:
    return {
        "source_text_required_pattern": r"[ぁ-んァ-ヶ一-龯ー]+",
        "source_residual_segment_pattern": r"[ぁ-んァ-ヶー]+",
        "line_width_count_pattern": r"\S",
        "residual_escape_sequence_pattern": r"\\[nrt]",
    }


@pytest.mark.asyncio
async def test_current_schema_creates_unified_rule_store(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    async with await registry.open_game(record.game_title) as session:
        rows = await session.connection.execute_fetchall(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ('rule_sets', 'rules', 'rule_domain_states')
            """,
        )

    table_names = {cast(str, row[0]) for row in rows}
    assert table_names == {"rule_sets", "rules", "rule_domain_states"}


def test_confirm_empty_is_stored_as_domain_state_not_fake_rule() -> None:
    report = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "mv_virtual_namebox",
            "rules_payload": {"rules": []},
            "game_context": {"engine_kind": "mv", "candidates": []},
            "settings_runtime_patterns": _valid_runtime_patterns(),
            "confirm_empty": True,
        }
    )

    assert report.status == "ok"
    runtime_summary = ensure_json_object(
        coerce_json_value(report.summary["rule_runtime"]),
        "rule_runtime",
    )
    assert runtime_summary["rule_count"] == 0
    domain_state = ensure_json_object(
        coerce_json_value(report.summary["domain_state"]),
        "domain_state",
    )
    assert domain_state["confirmed_empty"] is True
