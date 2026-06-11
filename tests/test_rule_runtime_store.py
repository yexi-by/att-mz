from pathlib import Path

import pytest

from app.persistence import GameRegistry


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

    assert {str(row[0]) for row in rows} == {"rule_sets", "rules", "rule_domain_states"}
