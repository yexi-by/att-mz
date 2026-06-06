# Debug Timings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the unified debug runtime, logging control, diagnostics timing output, and ordinary-mode timing-field cleanup described in `docs/superpowers/specs/2026-06-06-debug-timings-design.md`.

**Architecture:** Add a lightweight debug configuration parser and a contextvars-backed diagnostics context under `app.observability`. Route all stdout JSON through a shared injection helper, bridge existing timing fields into the diagnostics collector, and remove ordinary-mode timing fields from public summaries.

**Tech Stack:** Python 3.14, argparse, pydantic v2, loguru, contextvars, pytest, basedpyright.

---

### Task 1: Debug Configuration And Logging

**Files:**
- Modify: `setting.example.toml`
- Modify: `app/config/schemas.py`
- Modify: `app/cli/parser.py`
- Modify: `app/cli_main.py`
- Modify: `app/observability/logging.py`
- Create: `app/observability/diagnostics.py`
- Test: `tests/test_observability.py`
- Test: `tests/test_config_overrides.py`
- Test: `tests/test_cli_json_output.py`

- [x] **Step 1: Write failing tests for `[debug]`, CLI/env precedence, and logging cleanup**

Add tests that parse the new CLI switches, load only the debug TOML section, prove `ATT_MZ_DEBUG*` overrides setting values, and prove ordinary file logs no longer keep DEBUG messages.

- [x] **Step 2: Run focused RED tests**

Run: `uv run pytest tests/test_observability.py tests/test_config_overrides.py::test_setting_example_loads_debug_config tests/test_cli_json_output.py::test_global_debug_switches_parse -q`

Expected: FAIL because the parser, schema, and diagnostics module do not exist yet.

- [x] **Step 3: Implement debug schema and runtime settings**

Add strict pydantic models for `DebugSetting`, `DebugLoggingSetting`, and `DebugTimingsSetting`. Add `resolve_debug_runtime_settings()` with a light TOML reader that reads only `[debug]`, applies env and CLI overrides, and returns source metadata.

- [x] **Step 4: Implement logging level control**

Update `setup_logger()` to accept `file_level`. Change CLI startup so ordinary mode uses INFO file logs and debug logging uses configured console/file levels.

- [x] **Step 5: Run focused GREEN tests**

Run: `uv run pytest tests/test_observability.py tests/test_config_overrides.py tests/test_cli_json_output.py -q`

Expected: PASS for tests touched by this task or expose the next missing diagnostics pieces.

### Task 2: Diagnostics Context And Report Injection

**Files:**
- Modify: `app/observability/diagnostics.py`
- Modify: `app/observability/__init__.py`
- Modify: `app/agent_toolkit/reports.py`
- Modify: `app/cli/reports.py`
- Modify: `app/cli/commands/registry.py`
- Modify: `app/cli/commands/translation.py`
- Modify: `app/cli/commands/write_back.py`
- Modify: `app/cli_main.py`
- Test: `tests/test_observability.py`
- Test: `tests/test_cli_json_output.py`

- [x] **Step 1: Write failing tests for context isolation, diagnostics summary, and single file output**

Add tests for `current_diagnostics()`, nested async isolation, `summary.diagnostics`, and one diagnostics file per CLI run.

- [x] **Step 2: Run RED tests**

Run: `uv run pytest tests/test_observability.py tests/test_cli_json_output.py -q`

Expected: FAIL because the context and report helper are missing.

- [x] **Step 3: Implement diagnostics context**

Add `DiagnosticsContext`, `NoopDiagnosticsContext`, `current_diagnostics()`, `bind_diagnostics_context()`, stage timing, counters, artifacts, slowest timing summary, and JSON finalization.

- [x] **Step 4: Centralize report printing**

Add `inject_diagnostics_summary()` and `print_report()`. Update all direct `print(report.to_json_text())` command paths and top-level error printing to use the helper.

- [x] **Step 5: Run GREEN tests**

Run: `uv run pytest tests/test_observability.py tests/test_cli_json_output.py -q`

Expected: PASS for report and context tests.

### Task 3: Timing Field Cleanup And P0 Bridges

**Files:**
- Modify: `app/cli/reports.py`
- Modify: `app/agent_toolkit/services/text_index.py`
- Modify: `app/agent_toolkit/services/quality.py`
- Modify: `app/agent_toolkit/services/coverage.py`
- Modify: `app/application/handler.py`
- Modify: `app/application/use_cases/translation_run.py`
- Test: `tests/test_text_index.py`
- Test: `tests/test_agent_toolkit_quality_report.py`
- Test: `tests/test_cli_json_output.py`

- [x] **Step 1: Write failing tests for ordinary-mode cleanup and debug timing bridges**

Update tests so ordinary reports no longer contain `elapsed_ms`, `stage_timings`, `rust_stage_timings`, `rust_plan_ms`, `file_replacement_ms`, or `post_write_audit_ms`. Add debug-context tests that those values are bridged into diagnostics timings when enabled.

- [x] **Step 2: Run RED tests**

Run: `uv run pytest tests/test_text_index.py tests/test_agent_toolkit_quality_report.py tests/test_cli_json_output.py -q`

Expected: FAIL because old fields still leak and bridge calls are not in place.

- [x] **Step 3: Bridge existing timings**

Use `current_diagnostics().record_timing()` and `.counter()` at existing timing boundaries. Do not add extra scans or per-row measurements.

- [x] **Step 4: Remove ordinary summary timing fields**

Remove timing-only fields from public summary builders and service summaries while retaining business counts and status fields.

- [x] **Step 5: Run GREEN tests**

Run: `uv run pytest tests/test_text_index.py tests/test_agent_toolkit_quality_report.py tests/test_cli_json_output.py -q`

Expected: PASS after test updates and bridges.

### Task 4: Safety And Full Verification

**Files:**
- Test: `tests/test_observability.py`
- Test: `tests/test_cli_json_output.py`
- Test: `tests/test_config_overrides.py`
- Potentially modify implementation files from prior tasks only.

- [x] **Step 1: Add safety tests**

Assert diagnostics JSON does not include API keys, prompt content, model response text, game text, translation text, or per-location-path lists.

- [x] **Step 2: Run focused safety tests**

Run: `uv run pytest tests/test_observability.py tests/test_cli_json_output.py -q`

Expected: PASS.

- [x] **Step 3: Run required project gates**

Run: `uv run basedpyright`

Expected: 0 errors, 0 warnings.

Run: `uv run pytest`

Expected: all tests pass.
