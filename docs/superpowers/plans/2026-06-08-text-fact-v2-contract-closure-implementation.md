# Text Fact v2 Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Text Fact Contract v2 correctness gaps and split the touched code boundaries so current facts, saved translations, quality errors, rule validation, workspace validation, and write-back all use v2 fact identity instead of `location_path`.

**Architecture:** Rust rebuild produces v2 facts from non-deduplicated fact input rows and derives old warm-index rows separately. Python exposes a small `app/text_facts.py` facade backed by focused count, reader, and quality modules. Agent rule/workspace flows resolve native rule hits to current v2 fact identities before counting translated items or deleting stale translations.

**Tech Stack:** Python 3.14, pydantic v2, aiosqlite, pytest, basedpyright, Rust 2024, rusqlite, rayon, serde_json, cargo fmt, clippy, cargo test, uv.

---

## Scope Check

This plan implements the approved design in `docs/superpowers/specs/2026-06-08-text-fact-v2-contract-closure-design.md`.

The implementation is intentionally breaking for old test assets and old workspaces. Do not add compatibility fallbacks. If a saved translation, quality error, workspace item, or manual import entry lacks v2 identity, fail explicitly and tell the user to rebuild the current text index or export a fresh workspace.

Hard stop and return to design discussion if the implementation needs background state synchronization, a v1/v2 dual source of truth, path-based translated status for migrated flows, or a new broad service layer that every command must route through.

## File Structure

- Create `app/text_fact_core.py`: shared constants, `TextFactContractError`, scope loading, schema assertion, row decoding, chunking, conversion helpers.
- Create `app/text_fact_readers.py`: fact and translation item reads by path/fact_id, including all batched `IN` queries.
- Create `app/text_fact_counts.py`: current/pending/translated/stale/count SQL and count-only helper functions.
- Create `app/text_fact_quality.py`: quality-error fact reads, quality-check source reconstruction, and report sample details.
- Modify `app/text_facts.py`: facade that imports and re-exports public functions from the focused modules.
- Create `app/agent_toolkit/services/rule_identity.py`: resolve rule hit probes to current v2 facts, validate saved translation identity, and count translated rule hits by fact_id.
- Modify `app/agent_toolkit/services/common.py`: replace `translated_paths` report calculations with fact-id calculations.
- Modify `app/agent_toolkit/services/rule_validation.py`: rule validation/import reads current rule fact identity and deletes stale translations by fact_id.
- Modify `app/agent_toolkit/services/workspace.py`: workspace validation passes rule fact identity, not global translated paths.
- Modify `app/persistence/run_records.py`: quality errors require fact_id; path reads return all matching records without path-folding.
- Modify `app/rmmz/schema.py`: `TranslationErrorItem.fact_id` becomes required.
- Modify `app/agent_toolkit/services/manual_translation.py`: fact_id import helper uses the new batched reader.
- Modify `app/agent_toolkit/services/quality.py` and `app/agent_toolkit/services/common.py`: user-facing quality text does not expose `location_path` as a field name.
- Modify `rust/src/native_core/scope_index/rebuild.rs`: split fact rows from warm-index rows.
- Modify `rust/src/native_core/scope_index/storage.rs`: validate warm rows as a locator subset for facts, not as an equal-count identity set.
- Modify `rust/src/native_core/write_back_plan/repository.rs`: scope write-back preflight checks to allowed facts when allowed paths are provided.
- Modify `tests/_native_write_plan_helper.py`: remove `fact_identity_by_location`; read fact identity from inserted/current v2 facts.
- Modify tests in `tests/test_native_scope_index.py`, `tests/test_persistence.py`, `tests/test_agent_toolkit_rule_import.py`, `tests/test_agent_toolkit_workspace.py`, `tests/test_agent_toolkit_manual_import.py`, `tests/test_agent_toolkit_quality_report.py`, `tests/test_rmmz_write_plan.py`, and `tests/test_scan_budget.py`.
- Modify `README.md`, `CHANGELOG.md`, and `tests/test_release_notes.py` only for current user-facing contract and performance-boundary wording.

---

### Task 1: Rust Rebuild Keeps Same-Path v2 Facts

**Files:**
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Modify: `rust/src/native_core/scope_index/storage.rs`
- Test: `tests/test_native_scope_index.py`

- [ ] **Step 1: Write the failing rebuild test**

Add this test near the other `rebuild_native_scope_index_storage` tests in `tests/test_native_scope_index.py`:

```python
@pytest.mark.asyncio
async def test_rebuild_native_scope_index_storage_keeps_same_path_note_tag_facts(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """同一路径不同 NoteTag fact 必须同时进入 text_facts_v2。"""
    items_path = minimal_mv_game_dir / "www" / "data" / "Items.json"
    items = cast(list[object], json.loads(items_path.read_text(encoding="utf-8")))
    item = ensure_json_object(coerce_json_value(items[1]), "Items.json[1]")
    item["note"] = "<desc:回復薬>\n<desc:重複>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["desc"])]
        )

    setting = TextRulesSetting(source_text_required_pattern=r".+")
    result = rebuild_native_scope_index_storage(
        {
            "db_path": str(record.db_path),
            "game_path": str(minimal_mv_game_dir),
            "source_snapshot_fingerprint": "snapshot-v1",
            "rules_fingerprint": "rules-v1",
            "source_language": "ja",
            "target_language": "zh-Hans",
            "engine_kind": "mv",
            "text_rules_setting": setting.model_dump(mode="json"),
            "rule_candidate_text_rules": _rebuild_rule_candidate_text_rules(setting),
            "event_command_scope_codes": [101, 401],
            "source_text_required_pattern": setting.source_text_required_pattern,
            "created_at": "2026-06-08T00:00:00",
        }
    )

    assert result["status"] == "ok"
    assert _json_int(result["text_fact_count"], "text_fact_count") > _json_int(
        result["indexed_count"],
        "indexed_count",
    )
    with sqlite3.connect(record.db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = cast(
            list[sqlite3.Row],
            connection.execute(
                """
                SELECT fact_id, location_path, selector, raw_text, translatable_text
                FROM text_facts_v2
                WHERE domain = 'note_tag'
                    AND location_path = 'Items.json/1/note/desc'
                ORDER BY translatable_text
                """
            ).fetchall(),
        )
    assert len(rows) == 2
    assert {_sqlite_row_str(row, "translatable_text") for row in rows} == {"回復薬", "重複"}
    assert len({_sqlite_row_str(row, "fact_id") for row in rows}) == 2
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
uv run pytest tests/test_native_scope_index.py::test_rebuild_native_scope_index_storage_keeps_same_path_note_tag_facts -q
```

Expected: FAIL because only one `Items.json/1/note/desc` fact survives before v2 fact payload construction.

- [ ] **Step 3: Split fact rows from warm-index rows**

In `rust/src/native_core/scope_index/rebuild.rs`, replace the single post-scan `rows.sort_by` / `rows.dedup_by` block with this shape:

```rust
let mut fact_rows = rows;
fact_rows.sort_by(|left, right| {
    left.location_path
        .cmp(&right.location_path)
        .then(left.source_type.cmp(&right.source_type))
        .then(left.fact_selector.cmp(&right.fact_selector))
        .then(left.original_lines.cmp(&right.original_lines))
});
let warm_index_rows = warm_index_rows_from_fact_rows(&fact_rows);
```

Add a helper near the existing row helpers:

```rust
fn warm_index_rows_from_fact_rows(rows: &[DirectTextIndexRow]) -> Vec<DirectTextIndexRow> {
    let mut warm_rows = rows.to_vec();
    warm_rows.sort_by(|left, right| left.location_path.cmp(&right.location_path));
    warm_rows.dedup_by(|left, right| left.location_path == right.location_path);
    warm_rows
}
```

Use `fact_rows` for:

```rust
let text_fact_payload = build_text_fact_storage_payload_with_context(
    &fact_rows,
    &text_fact_scope,
    &data_files,
    Some(&context),
)?;
```

Use `warm_index_rows` for the warm-index summary and storage payload. Replace the existing `rows` references in those assignments with `warm_index_rows`:

```rust
let domain_summary = domain_summary_from_rows(&warm_index_rows);
let item_count = warm_index_rows.len();
```

The `DirectTextIndexRow` type must derive `Clone` for this helper. Change this line:

```rust
#[derive(Debug, Serialize)]
```

to:

```rust
#[derive(Clone, Debug, Serialize)]
```

- [ ] **Step 4: Loosen storage validation without hiding mismatches**

In `rust/src/native_core/scope_index/storage.rs`, remove the check that requires `payload.metadata.item_count == payload.text_facts.len()`. Replace `validate_text_index_fact_identities` with two checks:

```rust
fn validate_text_index_fact_identities(payload: &WriteStoragePayload) -> Result<(), String> {
    validate_warm_rows_have_matching_facts(payload)?;
    validate_facts_have_warm_locator_rows(payload)?;
    Ok(())
}

fn validate_warm_rows_have_matching_facts(payload: &WriteStoragePayload) -> Result<(), String> {
    let text_fact_identities = text_fact_identity_counts(&payload.text_facts);
    for row in &payload.text_index_rows {
        let identity = text_index_identity(
            row,
            row.text_fact_raw_text
                .clone()
                .unwrap_or_else(|| row.original_lines.join("\n")),
        );
        if !text_fact_identities.contains_key(&identity) {
            return Err(text_fact_identity_mismatch_error());
        }
    }
    Ok(())
}

fn validate_facts_have_warm_locator_rows(payload: &WriteStoragePayload) -> Result<(), String> {
    let warm_locations = payload
        .text_index_rows
        .iter()
        .map(|row| row.location_path.as_str())
        .collect::<BTreeSet<_>>();
    for fact in &payload.text_facts {
        if !warm_locations.contains(fact.location_path.as_str()) {
            return Err(text_fact_identity_mismatch_error());
        }
    }
    Ok(())
}
```

Keep `validate_text_fact_raw_identity_overrides` so warm rows with explicit raw overrides must still match exactly one fact.

- [ ] **Step 5: Update storage tests for warm-row subset semantics**

In `rust/src/native_core/scope_index/storage.rs` tests, rename `write_scope_index_storage_rejects_text_fact_count_mismatch` to `write_scope_index_storage_accepts_more_text_facts_than_warm_rows_when_locations_match`. Build one warm row and two facts sharing its `location_path` with different raw text. Assert:

```rust
assert_eq!(output.written_item_count, 1);
assert_eq!(output.text_fact_count, 2);
```

- [ ] **Step 6: Run focused Rust and Python tests**

Run:

```powershell
uv run pytest tests/test_native_scope_index.py::test_rebuild_native_scope_index_storage_keeps_same_path_note_tag_facts -q
cargo test --manifest-path rust/Cargo.toml scope_index::storage
```

Expected: both PASS.

- [ ] **Step 7: Commit**

```powershell
git add rust/src/native_core/scope_index/rebuild.rs rust/src/native_core/scope_index/storage.rs tests/test_native_scope_index.py
git commit -m "fix: 保留同路径 text fact"
```

---

### Task 2: Split Text Fact Python Adapter Boundaries

**Files:**
- Create: `app/text_fact_core.py`
- Create: `app/text_fact_readers.py`
- Create: `app/text_fact_counts.py`
- Create: `app/text_fact_quality.py`
- Modify: `app/text_facts.py`
- Test: existing tests importing `app.text_facts`

- [ ] **Step 1: Create the core module**

Move these definitions from `app/text_facts.py` into `app/text_fact_core.py`:

```python
"""Text Fact Contract v2 的共享基础能力。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import aiosqlite

from app.persistence.records import TextFactScopeV2Record, TextFactV2Record, TextIndexItemRecord
from app.persistence.rows import row_int, row_str
from app.persistence.sql import (
    TEXT_FACT_SCHEMA_VERSION,
    TEXT_FACT_SCOPE_V2_TABLE_NAME,
    TEXT_FACTS_V2_TABLE_NAME,
)
from app.rmmz.schema import ItemType
from app.rmmz.text_rules import JsonObject, coerce_json_value

if TYPE_CHECKING:
    from app.persistence import TargetGameSession

type SqlParameter = str | int

TEXT_FACT_SELECT_COLUMNS = """
        facts.fact_id,
        facts.schema_version,
        facts.domain,
        facts.location_path,
        facts.source_file,
        facts.source_type,
        facts.item_type,
        facts.role,
        facts.selector,
        facts.raw_text,
        facts.visible_text,
        facts.translatable_text,
        facts.raw_hash,
        facts.visible_hash,
        facts.translatable_hash,
        facts.scope_key
"""


class TextFactContractError(RuntimeError):
    """当前数据库无法按 Text Fact Contract v2 提供正文事实。"""
```

Move these functions into the same file without behavior changes:

```python
read_current_text_fact_scope_v2
assert_current_scope_fact_schema
read_count
chunks
text_fact_v2_from_row
text_fact_contract_error
item_type_from_text_fact
text_fact_lines
short_text_sample
display_name_from_index_record
terminology_owner_terms_from_index_record
locator_object_from_index_record
```

Rename private functions while moving:

```python
_assert_current_scope_fact_schema -> assert_current_scope_fact_schema
_read_count -> read_count
_chunks -> chunks
_text_fact_v2_from_row -> text_fact_v2_from_row
_text_fact_contract_error -> text_fact_contract_error
```

- [ ] **Step 2: Create reader/count/quality modules**

Move functions by responsibility:

```python
# app/text_fact_counts.py
count_current_text_facts_v2
count_pending_text_facts_v2
count_translated_text_facts_v2
count_writable_text_facts_v2
count_rule_hit_text_facts_v2
count_stale_translations_outside_writable_text_facts_v2
count_pending_text_fact_quality_errors_v2
count_pending_text_fact_quality_errors_by_type_v2
read_pending_text_fact_quality_error_paths_v2
read_pending_text_fact_quality_error_fact_ids_v2
read_text_fact_quality_error_paths_v2
read_text_fact_quality_error_fact_ids_v2
_pending_text_fact_count_sql
_pending_text_fact_quality_error_sql
_translation_matches_fact_sql
```

```python
# app/text_fact_readers.py
read_pending_text_fact_records_v2
read_current_text_fact_records_v2
read_unwritable_text_fact_records_v2
read_pending_text_fact_path_samples_v2
read_stale_translation_path_samples_outside_writable_text_facts_v2
read_pending_text_fact_translation_items
read_pending_text_fact_translation_data_map
read_current_text_fact_translation_data_map_v2
read_current_text_fact_placeholder_entries_v2
read_writable_text_fact_translation_items_by_paths
read_writable_text_fact_translation_items_v2
read_current_text_fact_translation_items_by_paths
read_writable_text_fact_translation_items_by_fact_ids
_read_current_text_facts_by_paths
_read_current_text_facts_by_fact_ids
_read_index_records_for_facts
```

```python
# app/text_fact_quality.py
read_text_fact_quality_items_for_translations
read_text_fact_sample_details_by_paths_v2
text_fact_records_to_translation_data_map
text_fact_record_to_translation_item
text_fact_record_to_quality_item
```

- [ ] **Step 3: Keep `app/text_facts.py` as a facade**

Replace `app/text_facts.py` contents with imports and `__all__`:

```python
"""Text Fact Contract v2 的 Python 适配层公开入口。"""

from app.text_fact_core import TextFactContractError, read_current_text_fact_scope_v2
from app.text_fact_counts import (
    count_current_text_facts_v2,
    count_pending_text_fact_quality_errors_by_type_v2,
    count_pending_text_fact_quality_errors_v2,
    count_pending_text_facts_v2,
    count_rule_hit_text_facts_v2,
    count_stale_translations_outside_writable_text_facts_v2,
    count_translated_text_facts_v2,
    count_writable_text_facts_v2,
    read_pending_text_fact_quality_error_fact_ids_v2,
    read_pending_text_fact_quality_error_paths_v2,
    read_text_fact_quality_error_fact_ids_v2,
    read_text_fact_quality_error_paths_v2,
)
from app.text_fact_quality import (
    read_text_fact_quality_items_for_translations,
    read_text_fact_sample_details_by_paths_v2,
    text_fact_record_to_quality_item,
    text_fact_record_to_translation_item,
    text_fact_records_to_translation_data_map,
)
from app.text_fact_readers import (
    read_current_text_fact_placeholder_entries_v2,
    read_current_text_fact_records_v2,
    read_current_text_fact_translation_data_map_v2,
    read_current_text_fact_translation_items_by_paths,
    read_pending_text_fact_path_samples_v2,
    read_pending_text_fact_records_v2,
    read_pending_text_fact_translation_data_map,
    read_pending_text_fact_translation_items,
    read_stale_translation_path_samples_outside_writable_text_facts_v2,
    read_unwritable_text_fact_records_v2,
    read_writable_text_fact_translation_items_by_fact_ids,
    read_writable_text_fact_translation_items_by_paths,
    read_writable_text_fact_translation_items_v2,
)

__all__ = [
    "TextFactContractError",
    "count_current_text_facts_v2",
    "count_pending_text_fact_quality_errors_by_type_v2",
    "count_pending_text_fact_quality_errors_v2",
    "count_pending_text_facts_v2",
    "count_rule_hit_text_facts_v2",
    "count_stale_translations_outside_writable_text_facts_v2",
    "count_translated_text_facts_v2",
    "count_writable_text_facts_v2",
    "read_current_text_fact_placeholder_entries_v2",
    "read_current_text_fact_records_v2",
    "read_current_text_fact_scope_v2",
    "read_current_text_fact_translation_data_map_v2",
    "read_current_text_fact_translation_items_by_paths",
    "read_pending_text_fact_path_samples_v2",
    "read_pending_text_fact_quality_error_fact_ids_v2",
    "read_pending_text_fact_quality_error_paths_v2",
    "read_pending_text_fact_records_v2",
    "read_pending_text_fact_translation_data_map",
    "read_pending_text_fact_translation_items",
    "read_stale_translation_path_samples_outside_writable_text_facts_v2",
    "read_text_fact_quality_error_fact_ids_v2",
    "read_text_fact_quality_error_paths_v2",
    "read_text_fact_quality_items_for_translations",
    "read_text_fact_sample_details_by_paths_v2",
    "read_unwritable_text_fact_records_v2",
    "read_writable_text_fact_translation_items_by_fact_ids",
    "read_writable_text_fact_translation_items_by_paths",
    "read_writable_text_fact_translation_items_v2",
    "text_fact_record_to_quality_item",
    "text_fact_record_to_translation_item",
    "text_fact_records_to_translation_data_map",
]
```

- [ ] **Step 4: Fix imports in new modules**

Use only direct imports between focused modules:

```python
from app.text_fact_core import (
    TEXT_FACT_SELECT_COLUMNS,
    assert_current_scope_fact_schema,
    chunks,
    item_type_from_text_fact,
    read_current_text_fact_scope_v2,
    read_count,
    text_fact_contract_error,
    text_fact_lines,
    text_fact_v2_from_row,
)
```

Do not import `app.text_facts` from the new modules. That would create facade-to-implementation cycles.

- [ ] **Step 5: Run import and type smoke tests**

Run:

```powershell
uv run python -c "import app.text_facts; print(app.text_facts.__all__[0])"
uv run pytest tests/test_agent_toolkit_quality_report.py::test_text_fact_v2_saved_translation_identity_uses_fact_id_not_path -q
```

Expected: command prints `TextFactContractError`; pytest PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/text_facts.py app/text_fact_core.py app/text_fact_readers.py app/text_fact_counts.py app/text_fact_quality.py
git commit -m "refactor: 拆分 text fact 适配层"
```

---

### Task 3: Quality Errors Require v2 Fact Identity

**Files:**
- Modify: `app/rmmz/schema.py`
- Modify: `app/persistence/run_records.py`
- Modify: `app/text_fact_quality.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/agent_toolkit/services/quality.py`
- Test: `tests/test_persistence.py`
- Test: `tests/test_agent_toolkit_quality_report.py`
- Test: `tests/test_rmmz_write_plan.py`

- [ ] **Step 1: Write failing persistence tests**

In `tests/test_persistence.py`, add:

```python
@pytest.mark.asyncio
async def test_translation_quality_errors_require_fact_id(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量错误属于当前 v2 fact，缺 fact_id 必须显式失败。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        with pytest.raises(ValueError, match="质量错误缺少 fact_id"):
            await session.write_translation_quality_errors(
                "run-1",
                [
                    TranslationErrorItem(
                        fact_id="",
                        location_path="Items.json/1/name",
                        item_type="short_text",
                        original_lines=["原文"],
                        translation_lines=["译文"],
                        error_type="AI漏翻",
                        error_detail={},
                        model_response="{}",
                    )
                ],
            )
```

Add a same-path multi-fact read test:

```python
@pytest.mark.asyncio
async def test_translation_quality_errors_by_paths_preserve_same_path_facts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """按路径过滤质量错误时不能折叠同一路径的不同 fact。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        await session.write_translation_quality_errors(
            "run-1",
            [
                TranslationErrorItem(
                    fact_id="fact-a",
                    location_path="Items.json/1/note/desc",
                    item_type="short_text",
                    original_lines=["一"],
                    translation_lines=["A"],
                    error_type="AI漏翻",
                    error_detail={},
                    model_response="{}",
                ),
                TranslationErrorItem(
                    fact_id="fact-b",
                    location_path="Items.json/1/note/desc",
                    item_type="short_text",
                    original_lines=["二"],
                    translation_lines=["B"],
                    error_type="AI漏翻",
                    error_detail={},
                    model_response="{}",
                ),
            ],
        )
        items = await session.read_translation_quality_errors_by_paths(
            "run-1",
            {"Items.json/1/note/desc"},
        )
    assert [item.fact_id for item in items] == ["fact-a", "fact-b"]
```

- [ ] **Step 2: Make `TranslationErrorItem.fact_id` required**

In `app/rmmz/schema.py`, change:

```python
fact_id: str | None = Field(default=None, exclude=True)
```

to:

```python
fact_id: str = Field(exclude=True)
```

Keep `exclude=True` so internal identity does not leak into model prompts.

- [ ] **Step 3: Reject missing fact_id on write**

In `app/persistence/run_records.py`, before serializing items:

```python
for error_item in items:
    if not error_item.fact_id:
        raise ValueError(
            f"质量错误缺少 fact_id，无法保存当前文本事实的检查结果: {error_item.location_path}"
        )
```

Serialize with `error_item.fact_id`, not `error_item.fact_id or ""`.

- [ ] **Step 4: Preserve all path-filtered quality errors**

Replace `quality_errors_by_path: dict[str, TranslationErrorItem]` in `read_translation_quality_errors_by_paths` with a list:

```python
quality_errors: list[TranslationErrorItem] = []
for batch in _chunks(sorted_paths, PATH_QUERY_BATCH_SIZE):
    placeholders = ", ".join("?" for _path in batch)
    async with self.connection.execute(
        f"""
--sql
            SELECT *
            FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
            WHERE run_id = ? AND location_path IN ({placeholders})
            ORDER BY location_path, fact_id
        ;
        """,
        (run_id, *batch),
    ) as cursor:
        rows = await cursor.fetchall()
    quality_errors.extend(self._decode_translation_quality_error(row) for row in rows)
return sorted(quality_errors, key=lambda item: (item.location_path, item.fact_id))
```

Keep `read_translation_quality_errors_by_fact_ids` keyed by fact_id because `fact_id` is unique for the run/fact pair.

- [ ] **Step 5: Change report mapping to fact_id**

In `app/text_fact_quality.py` and `app/agent_toolkit/services/common.py`, replace path-keyed quality error maps with fact-id maps:

```python
quality_errors_by_fact_id = {
    item.fact_id: item
    for item in quality_error_items
}
```

When building display details, use:

```python
"text_position": item.location_path
```

Do not emit an action sentence that contains the literal key name `location_path`.

- [ ] **Step 6: Update existing tests that build `TranslationErrorItem`**

Every `TranslationErrorItem` constructor call in tests must pass a real `fact_id`. Use the current fact from the same fixture setup:

```python
fact_id=target_item.fact_id or pytest.fail("测试目标译文缺少 fact_id")
```

Do not add `fact_id=""` except in the single failure test from Step 1.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
uv run pytest tests/test_persistence.py -q
uv run pytest tests/test_agent_toolkit_quality_report.py tests/test_rmmz_write_plan.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add app/rmmz/schema.py app/persistence/run_records.py app/text_fact_quality.py app/agent_toolkit/services/common.py app/agent_toolkit/services/quality.py tests/test_persistence.py tests/test_agent_toolkit_quality_report.py tests/test_rmmz_write_plan.py
git commit -m "fix: 强制质量错误使用 fact_id"
```

---

### Task 4: Fact-id Readers Are Batched and Path Readers Do Not Collapse Facts

**Files:**
- Modify: `app/text_fact_readers.py`
- Modify: `tests/test_scan_budget.py`
- Test: `tests/test_agent_toolkit_manual_import.py`

- [ ] **Step 1: Add scan budget coverage for the exported manual helper**

In `tests/test_scan_budget.py::test_task7_fact_id_helpers_use_batched_in_queries`, add:

```python
(text_facts_source, "read_writable_text_fact_translation_items_by_fact_ids"),
```

to the inspected functions list.

- [ ] **Step 2: Batch `read_writable_text_fact_translation_items_by_fact_ids`**

In `app/text_fact_readers.py`, change the helper to mirror `_read_current_text_facts_by_fact_ids`:

```python
facts: list[TextFactV2Record] = []
for batch in chunks(unique_fact_ids, 500):
    placeholders = ", ".join("?" for _fact_id in batch)
    async with session.connection.execute(
        f"""
--sql
            SELECT
{TEXT_FACT_SELECT_COLUMNS}
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
                AND indexed.writable = 1
            WHERE facts.scope_key = ?
                AND facts.fact_id IN ({placeholders})
            ORDER BY indexed.location_path, facts.domain, facts.fact_id
        ;
        """,
        (scope.scope_key, *batch),
    ) as cursor:
        rows = await cursor.fetchall()
    facts.extend(text_fact_v2_from_row(row, session=session) for row in rows)
```

- [ ] **Step 3: Keep path readers list-shaped**

In `read_writable_text_fact_translation_items_by_paths`, replace the single-fact path dictionary with grouped facts:

```python
facts_by_path: dict[str, list[TextFactV2Record]] = {}
for fact in facts:
    if fact.scope_key == scope.scope_key and fact.location_path in unique_paths:
        facts_by_path.setdefault(fact.location_path, []).append(fact)

index_records = await session.read_text_index_items_by_paths(unique_paths)
items: list[TranslationItem] = []
for record in index_records:
    if not record.writable:
        continue
    for fact in facts_by_path.get(record.location_path, []):
        items.append(text_fact_record_to_translation_item(fact, index_record=record))
```

This helper remains a user path filter. It must return every current fact at a requested path.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run pytest tests/test_scan_budget.py::test_task7_fact_id_helpers_use_batched_in_queries -q
uv run pytest tests/test_agent_toolkit_manual_import.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/text_fact_readers.py tests/test_scan_budget.py tests/test_agent_toolkit_manual_import.py
git commit -m "fix: 分块读取手动补译 fact"
```

---

### Task 5: Rule Hit Identity Replaces translated_paths

**Files:**
- Create: `app/agent_toolkit/services/rule_identity.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify: `app/agent_toolkit/services/workspace.py`
- Test: `tests/test_agent_toolkit_rule_import.py`
- Test: `tests/test_agent_toolkit_workspace.py`

- [ ] **Step 1: Create rule identity module**

Add `app/agent_toolkit/services/rule_identity.py`:

```python
"""Agent 规则命中与当前 v2 fact 身份的解析。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.persistence.records import TextFactV2ReadFilter, TextFactV2Record
from app.rmmz.schema import TranslationItem

if TYPE_CHECKING:
    from app.persistence import TargetGameSession


@dataclass(frozen=True, slots=True)
class RuleFactProbe:
    """规则扫描命中中可用于解析当前 v2 fact 的最小信息。"""

    domain: str
    location_path: str
    translatable_text: str


@dataclass(frozen=True, slots=True)
class RuleFactHit:
    """已解析到当前 v2 fact 的规则命中。"""

    fact_id: str
    location_path: str
    sample_text: str


def require_translation_fact_ids(items: Iterable[TranslationItem]) -> set[str]:
    """读取已保存译文 fact_id；缺失说明旧形状混入当前流程。"""
    fact_ids: set[str] = set()
    for item in items:
        if not item.fact_id:
            raise ValueError(f"已保存译文缺少 fact_id，无法判断当前事实身份: {item.location_path}")
        fact_ids.add(item.fact_id)
    return fact_ids


def count_translated_rule_hits(hits: Iterable[RuleFactHit], translated_fact_ids: set[str]) -> int:
    """按 fact_id 计算规则命中中已经成功保存译文的数量。"""
    return sum(1 for hit in hits if hit.fact_id in translated_fact_ids)


async def resolve_current_rule_fact_hits(
    session: TargetGameSession,
    probes: Sequence[RuleFactProbe],
) -> list[RuleFactHit]:
    """把规则命中解析到当前 v2 facts；未解析命中不冒充已翻译。"""
    if not probes:
        return []
    location_paths = sorted({probe.location_path for probe in probes})
    facts = await session.read_text_facts_v2(TextFactV2ReadFilter(location_paths=location_paths))
    facts_by_key: dict[tuple[str, str, str], list[TextFactV2Record]] = {}
    for fact in facts:
        key = (fact.domain, fact.location_path, fact.translatable_text)
        facts_by_key.setdefault(key, []).append(fact)
    hits: list[RuleFactHit] = []
    for probe in probes:
        key = (probe.domain, probe.location_path, probe.translatable_text)
        matched = facts_by_key.get(key, [])
        if len(matched) > 1:
            raise ValueError(f"当前规则命中解析到多个 v2 fact: {probe.location_path}")
        if len(matched) == 1:
            fact = matched[0]
            hits.append(
                RuleFactHit(
                    fact_id=fact.fact_id,
                    location_path=fact.location_path,
                    sample_text=fact.translatable_text,
                )
            )
    return hits
```

- [ ] **Step 2: Extend `_RuleHitMetric` to carry fact_id**

In `app/agent_toolkit/services/common.py`, change:

```python
@dataclass(frozen=True, slots=True)
class _RuleHitMetric:
    location_path: str
    sample_text: str
```

to:

```python
@dataclass(frozen=True, slots=True)
class _RuleHitMetric:
    location_path: str
    sample_text: str
    fact_id: str | None = None
```

Change `_build_rule_hit_metric_detail`:

```python
translated_fact_ids: set[str],
"translated_count": sum(
    1
    for hit in record_hits
    if hit.fact_id is not None and hit.fact_id in translated_fact_ids
),
```

Change `_build_rule_metric_detail` for `TranslationItem` sequences:

```python
translated_fact_ids: set[str],
"translated_count": sum(
    1
    for item in record_items
    if item.fact_id is not None and item.fact_id in translated_fact_ids
),
```

- [ ] **Step 3: Resolve NoteTag and plugin-source hit identities in validation**

In `app/agent_toolkit/services/rule_validation.py`, replace `translated_paths` reads with:

```python
translated_items = await session.read_translated_items_by_prefixes(prefixes)
translated_fact_ids = require_translation_fact_ids(translated_items)
rule_fact_hits = await resolve_current_rule_fact_hits(
    session,
    [
        RuleFactProbe(
            domain="note_tag",
            location_path=hit.location_path,
            translatable_text=hit.sample_text,
        )
        for hit in note_hit_metrics
    ],
)
```

For plugin-source use `domain="plugin_source"`.

When constructing `_RuleHitMetric`, pass the resolved fact id:

```python
resolved_by_probe = {
    (hit.location_path, hit.sample_text): hit.fact_id
    for hit in rule_fact_hits
}
_RuleHitMetric(
    location_path=raw_hit.location_path,
    sample_text=raw_hit.sample_text,
    fact_id=resolved_by_probe.get((raw_hit.location_path, raw_hit.sample_text)),
)
```

Unresolved hits remain visible in hit counts and samples but do not count as translated.

- [ ] **Step 4: Update plugin parameter and event-command validation**

For validation contexts that already produce `TranslationItem` objects, use:

```python
translated_fact_ids = require_translation_fact_ids(translated_plugin_items)
```

and count `item.fact_id in translated_fact_ids`. Do not call `session.read_translation_location_paths()`.

- [ ] **Step 5: Update workspace validation wrappers**

In `app/agent_toolkit/services/workspace.py`, delete:

```python
translated_paths = await session.read_translation_location_paths()
```

Each rule validation wrapper should obtain only the saved translations relevant to its rule family, then pass `translated_fact_ids` or resolved rule hit metrics to common report builders.

- [ ] **Step 6: Add same-path stale translated_count tests**

In `tests/test_agent_toolkit_rule_import.py`, add a test named:

```python
async def test_validate_note_tag_rules_does_not_count_same_path_stale_fact_as_translated(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
```

The test must:

1. Build current v2 facts with two same-path note facts.
2. Save a translation for only one fact.
3. Validate a rule that hits the other fact.
4. Assert `report.summary["translated_count"] == 0`.

Add a plugin-source translated-count test in Task 6 together with the plugin-source import-delete fixture. Do not add a separate plugin-source fixture in this task.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_does_not_count_same_path_stale_fact_as_translated -q
uv run pytest tests/test_agent_toolkit_workspace.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add app/agent_toolkit/services/rule_identity.py app/agent_toolkit/services/common.py app/agent_toolkit/services/rule_validation.py app/agent_toolkit/services/workspace.py tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workspace.py
git commit -m "fix: 按 fact_id 统计规则译文"
```

---

### Task 6: Rule Imports Delete Stale Translations by fact_id

**Files:**
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify: `app/agent_toolkit/services/rule_identity.py`
- Test: `tests/test_agent_toolkit_rule_import.py`

- [ ] **Step 1: Add stale fact deletion helper**

In `app/agent_toolkit/services/rule_identity.py`, add:

```python
def stale_translation_fact_ids(
    *,
    old_items: Sequence[TranslationItem],
    current_rule_hits: Sequence[RuleFactHit],
) -> list[str]:
    """计算规则变更后需要删除的旧译文 fact_id。"""
    old_fact_ids = require_translation_fact_ids(old_items)
    current_fact_ids = {hit.fact_id for hit in current_rule_hits}
    return sorted(old_fact_ids - current_fact_ids)
```

- [ ] **Step 2: Replace NoteTag path deletion**

In `import_note_tag_rules`, replace `old_note_paths`, `new_note_paths`, and `delete_translation_items_by_paths(stale_paths)` with:

```python
old_note_items = await session.read_translated_items_by_prefixes(_note_tag_rule_prefixes(old_records))
new_note_hits = await resolve_current_rule_fact_hits(session, new_note_probes)
stale_fact_ids = stale_translation_fact_ids(
    old_items=old_note_items,
    current_rule_hits=new_note_hits,
)

deleted_translation_items = 0
deleted_translation_backup_path: str | None = None
if stale_fact_ids:
    stale_items = await session.read_translated_items_by_fact_ids(stale_fact_ids)
    backup = await write_rule_import_translation_backup(
        game_title=game_title,
        domain="note-tag-rules",
        items=stale_items,
    )
    if backup is not None:
        deleted_translation_backup_path = backup.backup_path
    deleted_translation_items = await session.delete_translation_items_by_fact_ids(stale_fact_ids)
```

Delete `_translation_paths_matching_note_rules` if no production code uses it after this change.

- [ ] **Step 3: Replace plugin-source path deletion**

In `import_plugin_source_rules`, replace `old_paths`, `new_paths`, and `delete_translation_items_by_paths(stale_paths)` with the same fact-id flow:

```python
old_translated_items = await session.read_translated_items_by_prefixes(
    _plugin_source_rule_prefixes(old_records)
)
new_plugin_source_hits = await resolve_current_rule_fact_hits(session, new_plugin_source_probes)
stale_fact_ids = stale_translation_fact_ids(
    old_items=old_translated_items,
    current_rule_hits=new_plugin_source_hits,
)
```

Use `read_translated_items_by_fact_ids` for backup and `delete_translation_items_by_fact_ids` for deletion.

- [ ] **Step 4: Add import deletion tests**

In `tests/test_agent_toolkit_rule_import.py`, add:

```python
async def test_import_note_tag_rules_deletes_only_stale_fact_id_for_same_path(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
```

The test must assert:

```python
remaining_items = await session.read_translated_items()
assert {item.fact_id for item in remaining_items} == {current_fact_id}
```

Add:

```python
async def test_import_plugin_source_rules_deletes_only_stale_fact_id_for_same_path(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
```

using existing plugin-source rule fixtures. Assert that `delete_translation_items_by_paths` is not called by monkeypatching it to raise:

```python
async def forbidden_path_delete(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("规则导入不得按 location_path 删除译文")

monkeypatch.setattr(TargetGameSession, "delete_translation_items_by_paths", forbidden_path_delete)
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/agent_toolkit/services/rule_identity.py app/agent_toolkit/services/rule_validation.py tests/test_agent_toolkit_rule_import.py
git commit -m "fix: 规则导入按 fact_id 清理译文"
```

---

### Task 7: Write-back Preflight Checks Are Scoped

**Files:**
- Modify: `rust/src/native_core/write_back_plan/repository.rs`
- Test: `tests/test_rmmz_write_plan.py`
- Test: Rust tests under `rust/src/native_core/write_back_plan`

- [ ] **Step 1: Add a focused write-back test**

In `tests/test_rmmz_write_plan.py`, add a test that:

1. Creates two current writable facts.
2. Saves translations for both.
3. Calls write-back with `writable_location_paths` containing only the first path.
4. Adds a stale saved translation outside the allowed path.
5. Asserts the plan succeeds and writes only the allowed fact.

Name:

```python
async def test_write_back_allowed_paths_do_not_scan_unrelated_stale_translations(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
```

The assertion must include:

```python
assert planned.summary.data_item_count + planned.summary.plugin_item_count == 1
```

- [ ] **Step 2: Limit disallowed translation check to allowed paths**

In `rust/src/native_core/write_back_plan/repository.rs`, change `assert_no_disallowed_translation_items` SQL so allowed-path runs use:

```sql
WHERE facts.scope_key = ?
  AND facts.location_path IN ({placeholders})
```

When `allowed_paths` is empty, return before preparing this check.

- [ ] **Step 3: Limit unresolved/stale check to candidate fact ids**

Change `assert_all_translations_resolved_to_v2_facts` signature:

```rust
fn assert_all_translations_resolved_to_v2_facts(
    connection: &Connection,
    allowed_paths: &[String],
    resolved_fact_ids: &HashSet<String>,
) -> Result<(), String>
```

For allowed-path runs, query only translation rows whose `location_path` is in the allowed path set:

```sql
SELECT fact_id, location_path
FROM translation_items
WHERE location_path IN ({placeholders})
ORDER BY location_path, fact_id
```

For full write-back runs, keep the full table check.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run pytest tests/test_rmmz_write_plan.py::test_write_back_allowed_paths_do_not_scan_unrelated_stale_translations -q
cargo test --manifest-path rust/Cargo.toml write_back_plan
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rust/src/native_core/write_back_plan/repository.rs tests/test_rmmz_write_plan.py
git commit -m "fix: 收窄写回前置校验范围"
```

---

### Task 8: Remove Test Helper's Path Identity Model

**Files:**
- Modify: `tests/_native_write_plan_helper.py`
- Test: `tests/test_rmmz_write_plan.py`

- [ ] **Step 1: Replace path-keyed identity return**

In `tests/_native_write_plan_helper.py`, change `_insert_text_fact_v2_contract` to return:

```python
dict[str, tuple[str, str, str]]
```

keyed by `TranslationItem.fact_id` when present. For items without `fact_id`, create the fact row first, then assign the generated fact_id back to a local map keyed by object index:

```python
fact_identity_by_item_index[item_index] = (fact_id, raw_hash, translatable_hash)
```

Do not use `fact_identity_by_location`.

- [ ] **Step 2: Serialize temp translation rows by item identity**

Change `_translation_item_row_for_temp_db` signature:

```python
def _translation_item_row_for_temp_db(
    item: TranslationItem,
    item_index: int,
    fact_identity_by_item_index: dict[int, tuple[str, str, str]],
) -> tuple[str, str, str, str | None, str, str, str, str, str]:
```

Lookup by `item_index`:

```python
identity = fact_identity_by_item_index.get(item_index)
if identity is None:
    raise AssertionError(f"测试临时库缺少当前 v2 fact: index={item_index}, path={item.location_path}")
```

- [ ] **Step 3: Remove fake helper domain fallback**

Replace:

```python
return "test_helper"
```

in `_text_fact_domain_for_helper` with:

```python
raise AssertionError(f"测试 helper 不支持的当前文本事实路径: {location_path}")
```

This deletes the old second business model instead of expanding it.

- [ ] **Step 4: Run write plan tests**

Run:

```powershell
uv run pytest tests/test_rmmz_write_plan.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/_native_write_plan_helper.py tests/test_rmmz_write_plan.py
git commit -m "test: 删除写回测试 path 身份模型"
```

---

### Task 9: Scan Budget and Old Path Flow Deletion

**Files:**
- Modify: `tests/test_scan_budget.py`
- Modify: production files flagged by this test

- [ ] **Step 1: Strengthen scan budget assertions**

In `tests/test_scan_budget.py`, add a test named:

```python
def test_text_fact_v2_migrated_flows_do_not_use_translated_paths_sets() -> None:
    """迁移后的 Agent 主流程不得用 location_path 集合作为已翻译事实身份。"""
    checked_files = [
        Path("app/agent_toolkit/services/common.py"),
        Path("app/agent_toolkit/services/rule_validation.py"),
        Path("app/agent_toolkit/services/workspace.py"),
    ]
    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "translated_paths: set[str]" not in source
        assert "read_translation_location_paths()" not in source
        assert "if hit.location_path in translated_paths" not in source
        assert "if item.location_path in translated_paths" not in source
```

Extend existing location-join guard to include the new modules:

```python
Path("app/text_fact_counts.py"),
Path("app/text_fact_readers.py"),
Path("app/text_fact_quality.py"),
Path("app/agent_toolkit/services/rule_identity.py"),
```

- [ ] **Step 2: Remove old helper tests that assert path behavior**

Delete or rewrite tests whose only assertion is that `read_translation_location_paths()` drives translated_count. Replace each with a fact-id assertion. The old path behavior must not remain as an accepted test contract.

- [ ] **Step 3: Run scan budget**

Run:

```powershell
uv run pytest tests/test_scan_budget.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_scan_budget.py app/agent_toolkit/services/common.py app/agent_toolkit/services/rule_validation.py app/agent_toolkit/services/workspace.py app/text_fact_counts.py app/text_fact_readers.py app/text_fact_quality.py app/agent_toolkit/services/rule_identity.py
git commit -m "test: 阻止 translated_paths 回退"
```

---

### Task 10: User-facing Docs and Release Notes

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_release_notes.py`

- [ ] **Step 1: Clarify README command entry**

In the README current text fact contract section, keep examples entry-neutral or split source/release entries:

```markdown
源码运行：

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
```

发行包运行：

```powershell
.\att-mz.exe rebuild-text-index --game <游戏标题>
```
```

Do not present a source-only command as the general user command.

- [ ] **Step 2: Clarify CHANGELOG performance boundary**

In `CHANGELOG.md`, add a concrete note under Text Fact Contract v2:

```markdown
- 性能边界：自动测试和 scan budget 只证明当前实现没有回到旧 Python 全量范围和旧路径身份；真实游戏耗时仍需要维护者在目标样本运行 `rebuild-text-index`、`quality-report`、`export-pending-translations` 和 `write-translated` 的 `--debug-timings` 命令确认。
```

- [ ] **Step 3: Update release-note tests**

In `tests/test_release_notes.py`, assert the CHANGELOG contains:

```python
"真实游戏耗时"
"--debug-timings"
"scan budget"
```

- [ ] **Step 4: Run docs tests**

Run:

```powershell
uv run pytest tests/test_release_notes.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add README.md CHANGELOG.md tests/test_release_notes.py
git commit -m "docs: 说明 v2 性能验收边界"
```

---

### Task 11: Full Verification

**Files:**
- No source edits unless verification exposes a defect.

- [ ] **Step 1: Run Python type check**

Run:

```powershell
uv run basedpyright
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 2: Run Python tests**

Run:

```powershell
uv run pytest
```

Expected: all tests PASS.

- [ ] **Step 3: Run Rust formatting**

Run:

```powershell
cargo fmt --manifest-path rust/Cargo.toml -- --check
```

Expected: PASS with no diff.

- [ ] **Step 4: Run Rust clippy**

Run:

```powershell
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
```

Expected: PASS.

- [ ] **Step 5: Run Rust tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml
```

Expected: all tests PASS.

- [ ] **Step 6: Check Skill protocol drift**

Run even if Skill files were not edited, because README/contract wording changed near user workflow:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: PASS with no generated drift.

- [ ] **Step 7: Check working tree**

Run:

```powershell
git status --short
```

Expected: only intentionally untracked files remain. The existing untracked review plan `docs/superpowers/plans/2026-06-08-text-fact-v2-parallel-review.md` may still be present if the user has not asked to commit it.

- [ ] **Step 8: Final commit if verification fixes were needed**

When Step 1-6 exposes verification fixes after the previous task commits, stage only tracked files changed by those fixes:

```powershell
git add -u
git commit -m "fix: 收束 text fact v2 验证"
```

When Step 1-6 need no fixes, do not create an empty commit.

---

## Execution Notes

- Prefer one subagent per task. Tasks 1, 3, 5, 6, 7, and 8 can be implemented by separate workers only if their write sets are kept isolated and merged by the main agent between tasks.
- Do not keep compatibility tests that assert old `location_path` identity behavior. Replace them with fact-id behavior tests or delete them.
- Do not add a cache to bridge native hits and facts. Resolve facts from SQLite at the validation boundary and let unresolved proposed hits count as untranslated.
- Do not change user-facing JSON schema fields unless a test is updated in the same task. `location_path` may remain as a displayed locator, but must not be the correctness key.
