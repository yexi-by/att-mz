# Contract Amnesia Destructive Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved destructive cleanup in `docs/superpowers/specs/2026-06-09-contract-amnesia-destructive-cleanup-design.md` so runtime code, schema, docs, Skill, and tests express only the current contract.

**Architecture:** The cleanup is intentionally breaking: current code accepts current inputs, and non-current inputs fail as ordinary invalid state without recognition branches. The plan first removes P0 runtime branches and user-facing history wording, then renames schema/API surfaces away from versioned business names, then rewrites tests/docs/Skill around current contract behavior.

**Tech Stack:** Python 3.14, pydantic v2, aiosqlite, argparse, pytest, basedpyright, Rust 2024, PyO3, rusqlite, rayon, cargo fmt, clippy, cargo test, uv, Markdown, Skill protocol generator.

---

## Scope Check

This is one master implementation plan for one approved destructive cleanup spec. The work crosses Python, Rust, SQLite, Skill, README, docs, tests, and release notes, but the changes are coupled by one contract decision: current business naming and current runtime behavior must not preserve historical forms.

Hard stop and return to design discussion if any task seems to require:

- a compatibility layer for non-current databases, workspaces, environment names, model responses, or loader inputs;
- a migration command or migration guide;
- a test that recognizes a specific non-current form to prove it fails;
- README, Skill, CLI, or JSON text that explains a non-current form to current users;
- a second fact source parallel to the current SQLite/native text fact model.

Do not add sentinel tests named after removed forms. Test current behavior with neutral invalid states such as missing required fields, unsupported response types, schema mismatch, missing current locator data, or unknown configuration keys.

## File Structure

- Modify `app/config/environment.py`: remove history-specific environment detection and error formatting.
- Modify `tests/test_config_overrides.py` and `tests/test_cli_json_output.py`: rewrite tests around current env/config/argument behavior with neutral invalid inputs.
- Modify `app/translation/verify.py`: make translation response IDs current string-only data and remove numeric coercion.
- Modify `tests/test_translation_line_alignment.py` and related translation tests: assert current response schema failures without history-shaped naming.
- Modify `app/native_contract.py`, `app/native_scope_index.py`, `rust/src/native_core/scope_index/storage.rs`, `tests/test_native_adapters.py`, and `tests/test_native_scope_index.py`: reword native/schema contract failures as current-contract failures.
- Modify `app/rmmz/loader.py`, `app/rmmz/__init__.py`, write-back callers, and RMMZ tests: delete or reshape the compatible full loader so source and active-runtime views are explicit.
- Modify `app/text_fact_core.py`, `app/text_fact_quality.py`, `app/text_index.py`, `app/text_scope/`, `app/agent_toolkit/services/feedback.py`, and related tests: require current locator/fact data and replace history-shaped wording.
- Modify `app/persistence/schema/current.sql`, `app/persistence/sql.py`, `app/persistence/records.py`, `app/persistence/text_fact_records.py`, `app/persistence/translation_records.py`, `rust/src/native_core/scope_index/storage.rs`, `rust/src/native_core/write_back_plan/repository.rs`, and all callers: rename current text fact schema/API from versioned business names to current names.
- Modify `app/native_placeholder_scan.py`, `app/native_structured_placeholder_scan.py`, `app/native_note_tag_scan.py`, `app/application/__init__.py`, `app/application/flow_gate.py`, and tests: delete history-shaped adapter/helper descriptions and parameters.
- Modify `tests/agent_toolkit_contract_fixtures.py`, `tests/rmmz_writeback_contract_fixtures.py`, `tests/_native_write_plan_helper.py`, `tests/current_v2_scope.py`, and broad tests: replace migration/auto-stale helpers with current valid fixtures and neutral invalid fixtures.
- Modify `README.md`, `docs/wiki/`, `docs/guides/`, `skills/att-mz-protocol/`, `skills/att-mz/`, `skills/att-mz-release/`, `tests/test_skill_protocol.py`, and `tests/test_release_notes.py`: current docs and Skill describe current recovery actions only.
- Modify `CHANGELOG.md`: record the destructive change in an allowed historical location.

## Global Execution Rules

- Use TDD for behavior changes: write or rewrite a current-contract test first, run it to see the expected failure, implement, then rerun.
- Do not add tests that mention the removed form in the name, docstring, fixture name, or assertion message.
- Do not create temporary benchmark files, scripts, manifests, or generated data as committed assets.
- Full Python test suite is expensive in this project. Do not run bare `uv run pytest` during Tasks 1-11. Use only targeted test files, targeted test functions, basedpyright, Rust checks, Skill checks, and static audits until final verification. The only planned full pytest run is Task 12 Step 2.
- Commit boundaries in this plan are for execution sessions where commits are desired. If the user has not asked for commits, stop after verification and report unstaged changes.
- Preserve unrelated existing worktree changes. At plan creation time these included `rust/src/native_core/scope_index/mv_virtual_namebox.rs` and several untracked planning/review files.

---

### Task 1: Baseline Inventory And Contract Guardrails

**Files:**
- Read: `docs/superpowers/specs/2026-06-09-contract-amnesia-destructive-cleanup-design.md`
- Read: `docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md`
- Read: `app/`
- Read: `rust/src/`
- Read: `tests/`
- Read: `README.md`
- Read: `docs/wiki/`
- Read: `docs/guides/`
- Read: `skills/att-mz-protocol/`
- Read: `skills/att-mz/`
- Read: `skills/att-mz-release/`

- [ ] **Step 1: Confirm worktree state**

Run:

```powershell
git status --short
```

Expected: command succeeds. Record unrelated pre-existing modified or untracked files in the execution notes. Do not revert, stage, clean, or modify unrelated files.

- [ ] **Step 2: Capture current contract-memory inventory**

Run:

```powershell
rg -n 'text_facts_v2|text_fact_scope_v2|TextFactV2|TextFactScopeV2|TEXT_FACT_SCHEMA_VERSION|Text Fact Contract v2|v2 facts|legacy|fallback|compat|deprecated|旧索引正文|旧工作区|旧数据库|旧 runtime map|迁移数据库|过旧|旧调用点|旧报告同形|旧式测试译文|generated_stale|RPG_MAKER_TOOLS_' app rust/src tests README.md docs/wiki docs/guides skills/att-mz-protocol skills/att-mz skills/att-mz-release CHANGELOG.md
```

Expected: command returns the current cleanup inventory. Classify hits into current sources to clean, allowed historical locations, and legal ecosystem/business terms. Do not turn this inventory into a permanent test.

- [ ] **Step 3: Confirm Skill generator baseline**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: exits 0 before cleanup. If it fails, stop and inspect because Skill generated files are already drifting before this plan starts.

- [ ] **Step 4: Create a phase note for execution**

In the execution notes, record:

```text
Contract cleanup baseline:
- Source spec: docs/superpowers/specs/2026-06-09-contract-amnesia-destructive-cleanup-design.md
- Review report: docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md
- No compatibility layer, migration command, migration guide, or history-shaped sentinel tests are allowed.
```

No files are modified in this task.

---

### Task 2: Config And CLI Current Input Cleanup

**Files:**
- Modify: `app/config/environment.py`
- Modify: `tests/test_config_overrides.py`
- Modify: `tests/test_cli_json_output.py`

- [ ] **Step 1: Rewrite configuration tests around current inputs**

In `tests/test_config_overrides.py`, replace environment tests that name removed prefixes with current-contract tests:

```python
def test_environment_overrides_apply_current_llm_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATT_MZ_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("ATT_MZ_LLM_API_KEY", "current-key")

    overrides = load_environment_overrides()

    assert overrides.llm.base_url == "https://example.invalid/v1"
    assert overrides.llm.api_key == "current-key"
```

```python
def test_unknown_setting_key_is_reported_as_current_invalid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "setting.toml"
    config_path.write_text(
        """
[llm]
base_url = "https://example.invalid/v1"
api_key = "key"
unknown_key = "value"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        load_setting(config_path)

    message = str(exc_info.value)
    assert "unknown_key" in message
    assert "Extra inputs are not permitted" in message or "额外输入" in message
```

Use actual local helper names from `tests/test_config_overrides.py` while preserving this behavior and neutral naming.

- [ ] **Step 2: Rewrite CLI unknown argument tests with neutral names**

In `tests/test_cli_json_output.py`, replace removed-mode wording with a neutral unknown-argument case:

```python
def test_cli_unknown_global_argument_returns_json_argument_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main(["--not-a-current-option"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code != 0
    assert payload["status"] == "error"
    assert payload["error"]["category"] == "argument"
    assert "--not-a-current-option" in payload["error"]["message"]
```

Use the existing project helper if this file already wraps `cli_main`.

- [ ] **Step 3: Run focused RED tests**

Run:

```powershell
uv run pytest tests/test_config_overrides.py tests/test_cli_json_output.py -q
```

Expected: FAIL while `app/config/environment.py` still has history-specific detection or tests still assert history-shaped wording.

- [ ] **Step 4: Remove history-specific environment detection**

In `app/config/environment.py`, delete the history-specific prefix constant and helper functions:

```python
_LEGACY_ENV_PREFIX
_collect_legacy_environment_names
_legacy_env_name
_format_legacy_environment_error
```

Make `load_environment_overrides()` only read current environment variable names. The function should ignore unknown environment variables and only validate values for current keys it actually consumes.

Keep errors focused on current requirements:

```python
raise ValueError("LLM base_url 必须是当前 OpenAI 兼容接口地址")
```

Do not mention removed prefixes or removed variable names.

- [ ] **Step 5: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_config_overrides.py tests/test_cli_json_output.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit checkpoint if commits are enabled**

```powershell
git add app/config/environment.py tests/test_config_overrides.py tests/test_cli_json_output.py
git commit -m "fix: 收束当前配置入口"
```

---

### Task 3: Translation Response Current Schema

**Files:**
- Modify: `app/translation/verify.py`
- Modify: `tests/test_translation_line_alignment.py`
- Modify: `app/translation/context.py` only if prompt ID creation needs a type clarification

- [ ] **Step 1: Rewrite response ID type test**

In `tests/test_translation_line_alignment.py`, replace numeric-ID acceptance with a neutral invalid-type test:

```python
def test_translation_response_rejects_non_string_prompt_id() -> None:
    response = '[{"id": 1, "text": "你好"}]'

    with pytest.raises(ValidationError):
        TranslationResponse.model_validate_json(response)
```

If the file only tests through a higher-level function, assert the current parse path returns a quality/error result that says the response ID must be a string. The test name and assertion message must not describe the input as a previous format.

- [ ] **Step 2: Run focused RED test**

Run:

```powershell
uv run pytest tests/test_translation_line_alignment.py -k "response" -q
```

Expected: FAIL because `TranslationResponseItem.id` still accepts `int` or the matching path still coerces IDs.

- [ ] **Step 3: Restrict response item ID type**

In `app/translation/verify.py`, change:

```python
id: str | int
```

to:

```python
id: str
```

Remove ID coercion in response matching. Replace:

```python
prompt_id = str(response_item.id)
```

with:

```python
prompt_id = response_item.id
```

Keep prompt creation in `app/translation/context.py` string-based:

```python
prompt_id = str(sequence)
```

- [ ] **Step 4: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_translation_line_alignment.py tests/test_translation_cache_context.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit checkpoint if commits are enabled**

```powershell
git add app/translation/verify.py app/translation/context.py tests/test_translation_line_alignment.py
git commit -m "fix: 收紧翻译响应 ID 契约"
```

---

### Task 4: Current Contract Error Wording

**Files:**
- Modify: `app/native_contract.py`
- Modify: `app/native_scope_index.py`
- Modify: `app/text_fact_core.py`
- Modify: `app/agent_toolkit/services/feedback.py`
- Modify: `app/text_scope/write_probe.py`
- Modify: `rust/src/native_core/scope_index/storage.rs`
- Modify: `tests/test_native_adapters.py`
- Modify: `tests/test_native_scope_index.py`
- Modify: `tests/test_agent_toolkit_feedback.py`
- Modify: `tests/test_text_protocol.py` or related text fact tests if they assert current errors

- [ ] **Step 1: Rewrite native contract tests around current failure**

In `tests/test_native_adapters.py`, replace tests that name extension age with current contract failure assertions:

```python
def test_native_contract_requires_current_python_contract() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        ensure_native_contract_version(native_version=0)

    message = str(exc_info.value)
    assert "不满足当前 Python 契约" in message
    assert "重新构建原生扩展" in message
```

Use the existing helper signature for `ensure_native_contract_version`; if the function reads from `app._native`, monkeypatch that value instead of adding a new API.

- [ ] **Step 2: Rewrite schema mismatch tests around current database requirement**

In `tests/test_native_scope_index.py`, update schema mismatch assertions to expect current wording:

```python
assert "当前数据库结构不满足要求" in message
assert "重新注册游戏" in message or "重建文本索引" in message
```

Do not assert that specific history words are absent in unit tests. Absence is checked by the final static audit.

- [ ] **Step 3: Rewrite text fact and feedback error tests**

Update tests that assert “旧索引正文” to assert current text index/fact inconsistency:

```python
assert "当前文本事实与当前文本索引不一致" in message
assert "重新生成当前文本索引" in message
```

For workspace cleanup warnings, assert:

```python
assert "manifest 外文件" in warning["message"]
assert "不参与本轮处理" in warning["message"]
```

- [ ] **Step 4: Run focused RED tests**

Run:

```powershell
uv run pytest tests/test_native_adapters.py tests/test_native_scope_index.py tests/test_agent_toolkit_feedback.py tests/test_text_protocol.py -q
cargo test --manifest-path rust/Cargo.toml scope_index::storage
```

Expected: FAIL where current implementation still emits history-shaped wording.

- [ ] **Step 5: Update Python error wording**

Make these messages current-only:

```python
_CURRENT_NATIVE_CONTRACT_ERROR = "Rust 原生扩展不满足当前 Python 契约，请重新构建原生扩展后重试。"
```

```python
def text_fact_contract_error() -> TextFactContractError:
    return TextFactContractError(
        "当前文本事实与当前文本索引不一致，不能继续执行；请重新生成当前文本索引。"
    )
```

For feedback validation, reuse the same current text fact/index message instead of duplicating a second wording.

For workspace cleanup warnings, use:

```python
"manifest 外文件未列入本轮输入，不参与本轮处理；如需处理请重新准备工作区。"
```

For write probe:

```python
"当前插件源码扫描结果缺失，不能继续执行；请重新生成当前文本索引后重试。"
```

- [ ] **Step 6: Update Rust schema mismatch wording**

In `rust/src/native_core/scope_index/storage.rs`, change schema mismatch messages to current wording:

```rust
"当前数据库结构不满足要求，请使用当前版本重新注册游戏并重新生成当前文本索引。"
```

If the function has separate unreadable and mismatch branches, both branches must express current structure failure and current rebuild/register actions only.

- [ ] **Step 7: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_native_adapters.py tests/test_native_scope_index.py tests/test_agent_toolkit_feedback.py tests/test_text_protocol.py -q
cargo test --manifest-path rust/Cargo.toml scope_index::storage
```

Expected: PASS.

- [ ] **Step 8: Commit checkpoint if commits are enabled**

```powershell
git add app/native_contract.py app/native_scope_index.py app/text_fact_core.py app/agent_toolkit/services/feedback.py app/text_scope/write_probe.py rust/src/native_core/scope_index/storage.rs tests/test_native_adapters.py tests/test_native_scope_index.py tests/test_agent_toolkit_feedback.py tests/test_text_protocol.py
git commit -m "fix: 收束当前错误文案"
```

---

### Task 5: RMMZ Loader Source Boundary

**Files:**
- Modify: `app/rmmz/loader.py`
- Modify: `app/rmmz/__init__.py`
- Modify: `app/application/handler.py`
- Modify: `app/application/write_plan_applier.py`
- Modify: `tests/test_rmmz_source_snapshot.py`
- Modify: `tests/test_rmmz_file_transaction.py`
- Modify: `tests/test_rmmz_post_write_audit.py`
- Modify: all tests that call `load_game_data()`

- [ ] **Step 1: Rewrite loader tests around explicit views**

In `tests/test_rmmz_source_snapshot.py`, assert current source loading requires source snapshot files:

```python
def test_translation_source_view_requires_current_source_snapshot(minimal_mv_game_dir: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc_info:
        load_translation_source_game_data(minimal_mv_game_dir)

    assert "当前翻译来源快照" in str(exc_info.value)
```

In active runtime tests, assert active runtime loading reads current runtime files explicitly:

```python
def test_active_runtime_view_reads_current_runtime_files(minimal_mv_game_dir: Path) -> None:
    data = load_active_runtime_game_data(minimal_mv_game_dir)

    assert data.view == GameFileView.ACTIVE_RUNTIME
```

Use async variants if the current loader API is async.

- [ ] **Step 2: Run focused RED tests**

Run:

```powershell
uv run pytest tests/test_rmmz_source_snapshot.py tests/test_rmmz_file_transaction.py tests/test_rmmz_post_write_audit.py -q
```

Expected: FAIL while default loader behavior still allows implicit source/runtime fallback or tests still use the ambiguous entry.

- [ ] **Step 3: Remove or reshape `load_game_data()`**

Choose one current-only shape:

```python
def load_game_data_for_view(game_dir: Path, *, view: GameFileView) -> GameData:
    if view is GameFileView.TRANSLATION_SOURCE:
        return load_translation_source_game_data(game_dir)
    if view is GameFileView.ACTIVE_RUNTIME:
        return load_active_runtime_game_data(game_dir)
    raise ValueError(f"未知游戏文件视图: {view}")
```

Remove public export of ambiguous `load_game_data()` from `app/rmmz/__init__.py`. If internal callers still need a generic function, make `view` mandatory and require source backups for translation source view.

- [ ] **Step 4: Update callers**

Replace each production call:

```python
load_game_data(game_dir)
```

with the current explicit view:

```python
load_translation_source_game_data(game_dir)
```

or:

```python
load_active_runtime_game_data(game_dir)
```

based on the command responsibility. Write-back planning and translation source scans use translation source view; post-write audits and active runtime diagnostics use active runtime view.

- [ ] **Step 5: Update tests to explicit views**

Replace test helper calls with explicit current view helpers. Do not add a test that patches the removed loader by name. Current tests should prove the explicit source view and active runtime view each work.

- [ ] **Step 6: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_rmmz_source_snapshot.py tests/test_rmmz_file_transaction.py tests/test_rmmz_post_write_audit.py tests/test_write_back_transactions.py tests/test_font_replacement_transactions.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit checkpoint if commits are enabled**

```powershell
git add app/rmmz/loader.py app/rmmz/__init__.py app/application/handler.py app/application/write_plan_applier.py tests/test_rmmz_source_snapshot.py tests/test_rmmz_file_transaction.py tests/test_rmmz_post_write_audit.py tests/test_write_back_transactions.py tests/test_font_replacement_transactions.py
git commit -m "fix: 显式区分游戏文件视图"
```

---

### Task 6: Text Fact Locator Contract

**Files:**
- Modify: `app/text_fact_core.py`
- Modify: `app/text_fact_quality.py`
- Modify: `app/text_fact_readers.py`
- Modify: `app/text_index.py`
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Modify: `tests/test_text_protocol.py`
- Modify: `tests/test_text_index.py`
- Modify: `tests/test_native_scope_index.py`
- Modify: `tests/test_quality_gate_result.py`

- [ ] **Step 1: Add current locator failure tests**

In the text fact tests, add current-contract failure tests:

```python
def test_text_fact_translation_item_requires_current_index_locator() -> None:
    fact = make_current_text_fact_record(
        fact_id="fact-current-1",
        location_path="Map001.json/events/1/pages/0/list/0/parameters/0",
        translatable_text="こんにちは",
    )

    with pytest.raises(TextFactContractError) as exc_info:
        text_fact_record_to_translation_item(fact, index_record=None)

    assert "当前文本事实与当前文本索引不一致" in str(exc_info.value)
```

Use an existing current fact fixture if one exists. If not, create a neutral `make_current_text_fact_record()` helper in the test file that builds the current record type.

- [ ] **Step 2: Add quality source failure test**

In `tests/test_quality_gate_result.py`, rewrite the missing-source test to current wording:

```python
def test_quality_item_rehydrate_requires_current_text_fact() -> None:
    with pytest.raises(TextFactContractError) as exc_info:
        rehydrate_quality_item_from_current_fact(missing_fact_id="fact-missing")

    assert "当前文本事实" in str(exc_info.value)
```

Use the real helper names from the file; do not mention removed source fields in the test name or docstring.

- [ ] **Step 3: Run focused RED tests**

Run:

```powershell
uv run pytest tests/test_text_protocol.py tests/test_text_index.py tests/test_quality_gate_result.py tests/test_native_scope_index.py -q
```

Expected: FAIL while conversion code still accepts missing locator records or tests still use history-shaped fixture names.

- [ ] **Step 4: Require locator fields in Python conversion**

Change conversion functions so current index locator data is mandatory:

```python
def require_current_index_record(
    *,
    fact: TextFactRecord,
    index_record: TextIndexItemRecord | None,
) -> TextIndexItemRecord:
    if index_record is None:
        raise text_fact_contract_error()
    if not index_record.display_name:
        raise text_fact_contract_error()
    return index_record
```

Use this before building translation prompt items, quality items, placeholder inputs, and report samples. Do not silently return `None` or empty terminology owner terms when the current locator is required for the current command.

- [ ] **Step 5: Confirm Rust rebuild writes required locator data**

In `rust/src/native_core/scope_index/rebuild.rs`, ensure all current fact-producing paths populate the locator fields used by Python. If a domain cannot supply a locator, fail in Rust with a current structured error instead of letting Python continue with partial data.

- [ ] **Step 6: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_text_protocol.py tests/test_text_index.py tests/test_quality_gate_result.py tests/test_native_scope_index.py -q
cargo test --manifest-path rust/Cargo.toml scope_index::rebuild
```

Expected: PASS.

- [ ] **Step 7: Commit checkpoint if commits are enabled**

```powershell
git add app/text_fact_core.py app/text_fact_quality.py app/text_fact_readers.py app/text_index.py rust/src/native_core/scope_index/rebuild.rs tests/test_text_protocol.py tests/test_text_index.py tests/test_native_scope_index.py tests/test_quality_gate_result.py
git commit -m "fix: 要求当前文本定位信息"
```

---

### Task 7: Schema And API Naming Without Business Version

**Files:**
- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/sql.py`
- Modify: `app/persistence/records.py`
- Modify: `app/persistence/text_fact_records.py`
- Modify: `app/persistence/translation_records.py`
- Modify: `app/text_facts.py`
- Modify: `app/text_fact_core.py`
- Modify: `app/text_fact_counts.py`
- Modify: `app/text_fact_readers.py`
- Modify: `app/text_fact_quality.py`
- Modify: `app/text_index.py`
- Modify: `app/native_scope_index.py`
- Modify: `rust/src/native_core/scope_index/storage.rs`
- Modify: `rust/src/native_core/write_back_plan/repository.rs`
- Modify: tests that import text fact record/filter/scope names

- [ ] **Step 1: Write current schema name tests**

In `tests/test_persistence.py`, update schema assertions to current names:

```python
def test_current_schema_uses_current_text_fact_table_names(shared_schema_sql: str) -> None:
    assert "CREATE TABLE text_facts" in shared_schema_sql
    assert "CREATE TABLE text_fact_scope" in shared_schema_sql
```

The test should assert current expected names, not assert removed names are absent. Absence is checked in the final static audit.

- [ ] **Step 2: Rewrite persistence API tests to current names**

Rename imports and helpers in tests from versioned names to current names:

```python
TextFactRecord
TextFactScopeRecord
TextFactReadFilter
replace_text_facts
read_text_fact_scope
require_current_text_fact_scope
read_text_facts
count_text_facts
```

Keep `schema_version` assertions where they prove current database integrity.

- [ ] **Step 3: Run focused RED tests**

Run:

```powershell
uv run pytest tests/test_persistence.py tests/test_text_index.py tests/test_native_scope_index.py -q
cargo test --manifest-path rust/Cargo.toml scope_index::storage write_back_plan::repository
```

Expected: FAIL until schema/API names are changed.

- [ ] **Step 4: Rename SQLite tables and constants**

In `app/persistence/schema/current.sql`, rename current business tables:

```sql
text_facts
text_fact_scope
```

Update index names to current names as well, for example:

```sql
idx_text_facts_scope_key
idx_text_facts_location_path
idx_text_fact_scope_scope_key
```

In `app/persistence/sql.py`, rename constants:

```python
TEXT_FACTS_TABLE_NAME = "text_facts"
TEXT_FACT_SCOPE_TABLE_NAME = "text_fact_scope"
CURRENT_TEXT_FACT_SCHEMA_VERSION = 2
```

`CURRENT_TEXT_FACT_SCHEMA_VERSION` may keep numeric `2` as internal integrity data. It must not be used in user text or business object names.

- [ ] **Step 5: Rename Python record and session API**

Use current names:

```python
class TextFactRecord(BaseModel): ...
class TextFactScopeRecord(BaseModel): ...
class TextFactReadFilter(BaseModel): ...
```

Rename session methods:

```python
replace_text_facts
read_text_fact_scope
require_current_text_fact_scope
read_text_facts
read_text_fact_render_parts
read_text_fact_domain_payloads
count_text_facts
```

Do not keep aliases with removed names. Update all imports and callers in the same task.

- [ ] **Step 6: Rename Rust SQL and storage model references**

In Rust SQL strings and model names, use `text_facts` and `text_fact_scope`. Keep internal numeric schema checks through `CURRENT_TEXT_FACT_SCHEMA_VERSION` or a Rust equivalent. Rust errors must refer to current text facts, not versioned facts.

- [ ] **Step 7: Mechanical import cleanup**

Run:

```powershell
rg -n 'TextFactV2|TextFactScopeV2|TextFactV2ReadFilter|text_facts_v2|text_fact_scope_v2|TEXT_FACT_SCHEMA_VERSION|Text Fact Contract v2|v2 fact|v2 facts' app rust/src tests
```

Expected: no hits in current source/test paths except allowed historical records outside this task. Fix any current source/test hit by renaming to current contract language.

- [ ] **Step 8: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_persistence.py tests/test_text_index.py tests/test_native_scope_index.py tests/test_rmmz_write_plan.py tests/test_agent_toolkit_rule_import.py -q
cargo test --manifest-path rust/Cargo.toml scope_index::storage write_back_plan::repository
```

Expected: PASS.

- [ ] **Step 9: Commit checkpoint if commits are enabled**

```powershell
git add app/persistence/schema/current.sql app/persistence/sql.py app/persistence/records.py app/persistence/text_fact_records.py app/persistence/translation_records.py app/text_facts.py app/text_fact_core.py app/text_fact_counts.py app/text_fact_readers.py app/text_fact_quality.py app/text_index.py app/native_scope_index.py rust/src/native_core/scope_index/storage.rs rust/src/native_core/write_back_plan/repository.rs tests
git commit -m "refactor: 当前文本事实命名去版本化"
```

---

### Task 8: Adapter And Runtime Helper Deletion

**Files:**
- Modify: `app/text_scope/__init__.py`
- Modify: `app/text_scope/builder.py`
- Modify: `app/text_index.py`
- Modify: `app/native_placeholder_scan.py`
- Modify: `app/native_structured_placeholder_scan.py`
- Modify: `app/native_note_tag_scan.py`
- Modify: `app/application/__init__.py`
- Modify: `app/application/flow_gate.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/plugin_source_text/native_scan.py`
- Modify: `app/note_tag_text/extraction.py`
- Modify: related tests that import these helpers

- [ ] **Step 1: Inventory current helper consumers**

Run:

```powershell
rg -n 'TextScopeService|build_translation_data_map|text_index_items_to_scope|_HANDLER_EXPORTS|ensure_empty_rule_import_allowed|candidate_count=|旧报告同形|legacy Python|旧调用点|旧规则链路' app tests
```

Expected: returns current consumers and history-shaped comments. Use it as a temporary execution inventory only.

- [ ] **Step 2: Rewrite tests to current APIs**

For tests importing `TextScopeService`, `build_translation_data_map`, or `text_index_items_to_scope`, replace them with current text fact fixtures and current adapter calls. Neutral helper shape:

```python
def make_current_translation_item(*, fact_id: str, location_path: str, text: str) -> TranslationItem:
    return TranslationItem(
        id=fact_id,
        fact_id=fact_id,
        location_path=location_path,
        original_lines=[text],
        translation_lines=[],
    )
```

Use the actual current `TranslationItem` fields. The helper name must describe current test data, not removed adapters.

- [ ] **Step 3: Run focused RED tests**

Run:

```powershell
uv run pytest tests/test_text_index.py tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workspace.py tests/test_native_adapters.py -q
```

Expected: FAIL while tests or production still depend on removed helpers.

- [ ] **Step 4: Delete or isolate runtime helper exports**

Remove public exports that only served removed helper models:

```python
TextScopeService
build_translation_data_map
text_index_items_to_scope
```

If a helper still has a current production owner, rename its docstring and function name to current responsibility. Do not leave runtime comments saying it exists for non-current tests or non-current tools.

- [ ] **Step 5: Remove history-shaped adapter docstrings**

In native adapter wrappers, replace docstrings such as “返回旧报告同形明细” with current wording:

```python
"""返回当前规则候选明细。"""
```

Do not add a compatibility alias.

- [ ] **Step 6: Remove package-level history export path**

In `app/application/__init__.py`, either delete dynamic package-level handler exports or rewrite them as current lazy exports if they remain public API. If kept, docstring should say:

```python
"""应用层当前公开入口的懒加载导出。"""
```

- [ ] **Step 7: Remove unused `candidate_count` parameter**

In `app/application/flow_gate.py`, remove the `candidate_count` parameter from `ensure_empty_rule_import_allowed()` and update every caller. If report context needs candidate counts, pass them through the current report model instead.

- [ ] **Step 8: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_text_index.py tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workspace.py tests/test_native_adapters.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit checkpoint if commits are enabled**

```powershell
git add app/text_scope app/text_index.py app/native_placeholder_scan.py app/native_structured_placeholder_scan.py app/native_note_tag_scan.py app/application/__init__.py app/application/flow_gate.py app/agent_toolkit/services/common.py app/plugin_source_text/native_scan.py app/note_tag_text/extraction.py tests/test_text_index.py tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workspace.py tests/test_native_adapters.py
git commit -m "refactor: 删除非当前适配入口"
```

---

### Task 9: Test Fixture Remodel

**Files:**
- Modify: `tests/agent_toolkit_contract_fixtures.py`
- Modify: `tests/rmmz_writeback_contract_fixtures.py`
- Modify: `tests/_native_write_plan_helper.py`
- Modify: `tests/current_v2_scope.py` or replace it with a current-named fixture module
- Modify: `tests/test_agent_toolkit_coverage.py`
- Modify: `tests/test_workflow_gate.py`
- Modify: `tests/test_scan_budget.py`
- Modify: `tests/test_persistence.py`
- Modify: `tests/test_native_adapters.py`
- Modify: tests that call removed fixture functions

- [ ] **Step 1: Create current fixture naming**

Rename `tests/current_v2_scope.py` to a current name such as:

```powershell
git mv tests/current_v2_scope.py tests/current_text_fact_scope.py
```

Update imports to current names:

```python
from tests.current_text_fact_scope import build_current_text_fact_scope
```

Do not keep an import alias with the removed name.

- [ ] **Step 2: Replace normal write helpers**

In `tests/agent_toolkit_contract_fixtures.py` and `tests/rmmz_writeback_contract_fixtures.py`, replace migration-shaped helpers with current-only helpers:

```python
async def write_current_translations(
    session: TargetGameSession,
    items: Sequence[TranslationItem],
) -> None:
    for item in items:
        if not item.fact_id:
            raise AssertionError(f"测试译文缺少当前 fact_id: {item.location_path}")
    await session.replace_translation_items(items)
```

Use the actual session method for saving translations. The helper must not generate fact IDs, stale records, or converted rows.

- [ ] **Step 3: Create explicit invalid-state fixture**

If a test needs a non-current database row, create a neutral fixture:

```python
async def insert_translation_with_missing_current_fact(
    session: TargetGameSession,
    *,
    location_path: str,
    translated_text: str,
) -> None:
    await session.execute_for_test(
        """
        INSERT INTO translation_items (
            location_path,
            original_text,
            translated_text,
            status
        ) VALUES (?, ?, ?, 'translated')
        """,
        (location_path, "", translated_text),
    )
```

Use an existing test-only SQL helper if available. This fixture name describes current invalid state; it must not use history-shaped words.

- [ ] **Step 4: Remove auto-generated stale rows**

Delete helper behavior that creates generated stale records inside normal write paths. If a test needs stale current data, it must call a dedicated neutral fixture by name.

- [ ] **Step 5: Rewrite scan budget wording**

In `tests/test_scan_budget.py` and `tests/scan_budget_contract.py`, remove source-text assertions whose only proof is that a non-current helper name does not appear. Keep scan budget tests focused on measurable current behavior:

```python
def test_translated_status_uses_current_fact_identity_for_same_path_items(
    current_same_path_fact_items: list[TranslationItem],
) -> None:
    first, second = current_same_path_fact_items
    translated_fact_ids = {first.fact_id}
    status_by_fact_id = {
        item.fact_id: item.fact_id in translated_fact_ids
        for item in current_same_path_fact_items
    }

    assert status_by_fact_id == {
        first.fact_id: True,
        second.fact_id: False,
    }
```

Use the actual current fixture and helper names in this test file. The assertion message, if needed, should say:

```python
"当前译文状态必须按 fact_id 判断"
```

Do not mention a removed path, fallback, or helper in this behavior test. Source keyword checks happen only in Task 11 as a delivery audit.

- [ ] **Step 6: Run focused RED tests**

Run:

```powershell
uv run pytest tests/test_scan_budget.py tests/test_agent_toolkit_coverage.py tests/test_workflow_gate.py tests/test_persistence.py tests/test_native_adapters.py -q
```

Expected: FAIL while imports or helper behavior still use removed fixture names.

- [ ] **Step 7: Update all callers**

Run:

```powershell
rg -n 'current_v2_scope|items_to_migrate|migrated_items|generated_stale|write_v2|make_current|legacy|fallback|old|旧|迁移|回退' tests
```

Expected: use the output to update current test paths. Allowed hits must be legitimate English sample text or allowed historical records outside tests. Do not add a permanent unit test for this keyword scan.

- [ ] **Step 8: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_scan_budget.py tests/test_agent_toolkit_coverage.py tests/test_workflow_gate.py tests/test_persistence.py tests/test_native_adapters.py tests/test_agent_toolkit_rule_import.py tests/test_write_back_transactions.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit checkpoint if commits are enabled**

```powershell
git add tests
git commit -m "test: 重塑当前契约夹具"
```

---

### Task 10: README, Docs, Skill, And Release Notes

**Files:**
- Modify: `README.md`
- Modify: `docs/wiki/`
- Modify: `docs/guides/`
- Modify: `skills/att-mz-protocol/`
- Modify: `skills/att-mz/`
- Modify: `skills/att-mz-release/`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_skill_protocol.py`
- Modify: `tests/test_release_notes.py`

- [ ] **Step 1: Rewrite docs tests around current facts**

In `tests/test_skill_protocol.py`, replace tests that require removed recovery terms with current observable requirements:

```python
def test_skill_cli_contract_documents_current_rebuild_actions() -> None:
    text = (ROOT / "skills" / "att-mz-protocol" / "templates" / "references" / "cli-command-contract.md.in").read_text(
        encoding="utf-8"
    )

    assert "rebuild-text-index" in text
    assert "prepare-agent-workspace" in text
    assert "当前文本索引" in text
    assert "当前工作区" in text
```

In `tests/test_release_notes.py`, keep release/history assertions in `CHANGELOG.md` only. Do not require README or Skill to mention removed forms.

- [ ] **Step 2: Run RED docs checks**

Run:

```powershell
uv run pytest tests/test_skill_protocol.py tests/test_release_notes.py -q
uv run python scripts/generate_skill_protocol.py --check
```

Expected: pytest may fail while current docs still contain removed wording or tests still require it. Skill check should pass before edits; after canonical edits and before generation it should fail, then pass after generation.

- [ ] **Step 3: Update Skill canonical source**

Edit only `skills/att-mz-protocol/` first. Current wording rules:

```text
当前文本索引缺失或不一致时，重新运行 rebuild-text-index。
当前工作区不符合本轮 manifest 时，重新运行 prepare-agent-workspace。
当前运行文件映射不可信时，重新生成当前运行文件。
```

Do not explain removed database names, removed workspace shapes, removed environment names, or removed runtime map names.

- [ ] **Step 4: Generate Skill outputs**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --write
```

Expected: `skills/att-mz/` and `skills/att-mz-release/` update from canonical source.

- [ ] **Step 5: Update README and current docs**

Rewrite current README/wiki/guides wording:

```markdown
当前文本索引缺失或与当前数据库状态不一致时，先运行：

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
```
```

Use placeholder paths such as `<游戏标题>` and `<工作区>`. Do not include local machine paths.

- [ ] **Step 6: Update CHANGELOG**

Add a concrete destructive-change note in `CHANGELOG.md`:

```markdown
- 契约失忆化清理：当前文本事实、工作区、运行文件映射和模型响应只按当前契约处理；不符合当前契约的数据需要重新注册游戏、重新导入规则、重新生成文本索引或重新准备工作区。
```

This is an allowed historical/release location.

- [ ] **Step 7: Run GREEN docs checks**

Run:

```powershell
uv run pytest tests/test_skill_protocol.py tests/test_release_notes.py -q
uv run python scripts/generate_skill_protocol.py --check
```

Expected: PASS with no generated Skill drift.

- [ ] **Step 8: Commit checkpoint if commits are enabled**

```powershell
git add README.md docs/wiki docs/guides skills/att-mz-protocol skills/att-mz skills/att-mz-release CHANGELOG.md tests/test_skill_protocol.py tests/test_release_notes.py
git commit -m "docs: 收束当前契约文档"
```

---

### Task 11: Static Current-Contract Audit

**Files:**
- Read: `app/`
- Read: `rust/src/`
- Read: `tests/`
- Read: `README.md`
- Read: `docs/wiki/`
- Read: `docs/guides/`
- Read: `skills/att-mz-protocol/`
- Read: `skills/att-mz/`
- Read: `skills/att-mz-release/`
- Read: `CHANGELOG.md`

- [ ] **Step 1: Run current source keyword audit**

Run:

```powershell
rg -n 'text_facts_v2|text_fact_scope_v2|TextFactV2|TextFactScopeV2|TextFactV2ReadFilter|TEXT_FACT_SCHEMA_VERSION|Text Fact Contract v2|v2 facts|legacy|fallback|compat|deprecated|旧索引正文|旧工作区|旧数据库|旧 runtime map|迁移数据库|过旧|旧调用点|旧报告同形|旧式测试译文|generated_stale|RPG_MAKER_TOOLS_' app rust/src tests README.md docs/wiki docs/guides skills/att-mz-protocol skills/att-mz skills/att-mz-release
```

Expected: no current-contract hits. Any hit must be fixed unless it is a legal ecosystem/business term such as `/v1`, dependency versions, RPG Maker engine versions, or font replacement business data.

- [ ] **Step 2: Run allowed historical location audit**

Run:

```powershell
rg -n 'text_facts_v2|Text Fact Contract v2|RPG_MAKER_TOOLS_|旧工作区|旧数据库|迁移|兼容' CHANGELOG.md docs/records docs/archive
```

Expected: hits are allowed only as release/history/review records and must not instruct current runtime, README, Skill, or tests to use them as facts.

- [ ] **Step 3: Run docs privacy audit**

Run:

```powershell
rg -n 'C:\\Users|/Users/|真实路径|本机路径|夜袭|Desktop|<样本根目录>|样本根目录' README.md docs/wiki docs/guides skills/att-mz-protocol skills/att-mz skills/att-mz-release CHANGELOG.md
```

Expected: no private local path or real user path. Placeholder paths such as `<游戏标题>` and `<工作区>` are allowed.

- [ ] **Step 4: Run current helper audit**

Run:

```powershell
rg -n 'items_to_migrate|migrated_items|generated_stale|write_v2|current_v2_scope|read_translation_location_paths\\(|delete_translation_items_by_paths\\(' tests app
```

Expected: no helper or production path keeps migration-shaped normal flow. Path-based translation deletion may remain only where the current public contract still explicitly deletes by current location path and is not used as fact identity.

- [ ] **Step 5: Fix audit findings**

For every non-allowed hit, fix the underlying source. Do not add unit tests that assert the keyword is absent. The audit is a delivery gate, not a runtime contract.

- [ ] **Step 6: Commit checkpoint if commits are enabled**

```powershell
git add app rust/src tests README.md docs/wiki docs/guides skills/att-mz-protocol skills/att-mz skills/att-mz-release CHANGELOG.md
git commit -m "chore: 通过当前契约静态审计"
```

---

### Task 12: Full Verification

**Files:**
- All files touched by Tasks 2-11.

- [ ] **Step 1: Run Python type check**

Run:

```powershell
uv run basedpyright
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 2: Run Python tests**

This is the only step in this plan that may run the full Python test suite. Earlier tasks must keep using targeted pytest commands because full `uv run pytest` takes about 5 minutes in this project.

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

Expected: no formatting changes required.

- [ ] **Step 4: Run Rust clippy**

Run:

```powershell
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
```

Expected: PASS with 0 warnings.

- [ ] **Step 5: Run Rust tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml
```

Expected: all Rust tests PASS.

- [ ] **Step 6: Run Skill protocol drift check**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: exits 0 with no generated drift.

- [ ] **Step 7: Run static current-contract audit again**

Run the Task 11 Step 1-4 commands again.

Expected: no current-contract source hits outside legal ecosystem/business terms or allowed historical locations.

- [ ] **Step 8: Run whitespace diff check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 9: Inspect final git status**

Run:

```powershell
git status --short
```

Expected: only intended files changed. Existing unrelated user changes remain untouched.

- [ ] **Step 10: Final delivery note**

Final response after execution must include:

- implemented scope by task;
- verification commands and exact results;
- static current-contract audit result;
- files not verified and why;
- remaining risks;
- whether commits were created;
- confirmation that no migration command, migration guide, compatibility layer, or history-shaped sentinel test was added.

---

## Self-Review Checklist

- [ ] Spec coverage: every section in `2026-06-09-contract-amnesia-destructive-cleanup-design.md` maps to a task.
- [ ] No compatibility layer, migration command, or migration guide is planned.
- [ ] Tests are written around current valid/invalid states, not removed forms.
- [ ] Schema/API current naming is addressed across SQLite, Python, Rust, tests, docs, and Skill.
- [ ] Skill changes start from `skills/att-mz-protocol/` and use the generator.
- [ ] Static keyword audits are delivery gates only; they are not introduced as runtime or unit-test sentinels.
- [ ] Full verification includes `uv run basedpyright`, `uv run pytest`, Rust format, clippy, tests, and Skill protocol check.
