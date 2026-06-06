# Debug LLM Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `debug.llm_messages` feature described in `docs/superpowers/specs/2026-06-07-debug-llm-messages-design.md`.

**Architecture:** Extend the existing debug runtime resolver so LLM message settings share the same CLI/env/setting precedence as timings. Add a focused `app.observability.llm_messages` runtime that records successful `LLMHandler.get_ai_response()` calls, writes Markdown files immediately, and finalizes an `index.md` at CLI shutdown.

**Tech Stack:** Python 3.14, pydantic v2 settings models, argparse, contextvars, pathlib, OpenAI compatible `AsyncOpenAI`, pytest, basedpyright.

---

## File Structure

- Modify `app/config/schemas.py`: add `DebugLLMMessagesSetting` and include it in `DebugSetting`.
- Modify `app/config/__init__.py`: export the new config model.
- Modify `setting.example.toml`: document `[debug.llm_messages]`.
- Modify `app/observability/diagnostics.py`: add `ATT_MZ_DEBUG_LLM_MESSAGES`, runtime fields, and resolver support.
- Create `app/observability/llm_messages.py`: own recorder, no-op recorder, context binding, Markdown rendering, redaction, index writing, and write errors.
- Modify `app/observability/__init__.py`: export LLM message runtime APIs.
- Modify `app/cli/parser.py`: add `--debug-llm-messages` and `--no-debug-llm-messages`.
- Modify `app/cli_main.py`: validate explicit CLI usage, bind/finalize recorder, and report write failures.
- Modify `app/llm/handler.py`: preserve base URL and redacted API key display, pass successful calls to current recorder.
- Modify `app/translation/retry.py`: forward `task_key` to `LLMHandler` and keep recorder write errors out of LLM retry classification.
- Modify `app/translation/text_translation.py`: pass `task_key="text-translation"`.
- Modify tests in `tests/test_config_overrides.py`, `tests/test_observability.py`, `tests/test_cli_json_output.py`, and `tests/test_translation_run_limits.py` as needed.

---

### Task 1: Config and CLI Contract

**Files:**
- Modify: `app/config/schemas.py`
- Modify: `app/config/__init__.py`
- Modify: `app/observability/diagnostics.py`
- Modify: `app/cli/parser.py`
- Modify: `setting.example.toml`
- Test: `tests/test_config_overrides.py`
- Test: `tests/test_observability.py`

- [x] **Step 1: Write failing config tests**

Add tests that validate `[debug.llm_messages]`, `ATT_MZ_DEBUG_LLM_MESSAGES`, CLI precedence, output dir, and parser attributes.

- [x] **Step 2: Run focused tests and confirm RED**

Run:

```bash
uv run pytest tests/test_config_overrides.py tests/test_observability.py -q
```

Expected: tests fail because `DebugSetting.llm_messages`, `debug_llm_messages`, and `ATT_MZ_DEBUG_LLM_MESSAGES` do not exist yet.

- [x] **Step 3: Implement config and parser fields**

Add pydantic config, parser flags, runtime setting fields, resolver logic, and setting example entries.

- [x] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
uv run pytest tests/test_config_overrides.py tests/test_observability.py -q
```

Expected: config/parser/debug runtime tests pass.

---

### Task 2: LLM Message Recorder

**Files:**
- Create: `app/observability/llm_messages.py`
- Modify: `app/observability/__init__.py`
- Test: `tests/test_observability.py`

- [x] **Step 1: Write failing recorder tests**

Cover successful write, lazy run-dir creation, `index.md`, API key and nested secret redaction, dynamic fenced blocks, Markdown table escaping, no-op behavior, and write failure raising `LLMMessageWriteError`.

- [x] **Step 2: Run focused tests and confirm RED**

Run:

```bash
uv run pytest tests/test_observability.py -q
```

Expected: tests fail because `app.observability.llm_messages` does not exist.

- [x] **Step 3: Implement recorder and Markdown helpers**

Implement `LLMMessageRecorder`, `NoopLLMMessageRecorder`, `LLMMessageRequest`, contextvar binding, safe file names, redaction, fenced block selection, table escaping, per-call Markdown, and final index writing.

- [x] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
uv run pytest tests/test_observability.py -q
```

Expected: recorder tests pass.

---

### Task 3: LLMHandler and Retry Integration

**Files:**
- Modify: `app/llm/handler.py`
- Modify: `app/translation/retry.py`
- Modify: `app/translation/text_translation.py`
- Test: `tests/test_observability.py`
- Test: `tests/test_translation_run_limits.py`

- [x] **Step 1: Write failing LLM integration tests**

Add tests proving `LLMHandler.get_ai_response()` records successful calls, does not record empty/failing responses, records API-success responses even when later verification fails, and `LLMMessageWriteError` is not retried as an LLM failure.

- [x] **Step 2: Run focused tests and confirm RED**

Run:

```bash
uv run pytest tests/test_observability.py tests/test_translation_run_limits.py -q
```

Expected: tests fail because `LLMHandler` has no recorder integration and `request_with_recoverable_retry()` has no `task_key`.

- [x] **Step 3: Implement LLM integration**

Persist safe request metadata in `LLMHandler.configure()`, call the current recorder after non-empty content is received, add optional `task_key`/`task_label`, and make retry bypass `LLMMessageWriteError`.

- [x] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
uv run pytest tests/test_observability.py tests/test_translation_run_limits.py -q
```

Expected: LLM integration tests pass.

---

### Task 4: CLI Lifecycle and Validation

**Files:**
- Modify: `app/cli_main.py`
- Test: `tests/test_cli_json_output.py`

- [x] **Step 1: Write failing CLI lifecycle tests**

Add tests for explicit `--debug-llm-messages` without `--debug`, explicit non-LLM command usage, `--no-debug-llm-messages` on non-LLM commands, setting/env enabled on non-LLM command not creating a directory, and recorder finalize artifact behavior.

- [x] **Step 2: Run focused tests and confirm RED**

Run:

```bash
uv run pytest tests/test_cli_json_output.py -q
```

Expected: tests fail because CLI validation and recorder lifecycle are not implemented.

- [x] **Step 3: Implement CLI lifecycle**

Create `LLM_MESSAGE_COMMANDS`, validate explicit CLI usage after resolving debug settings, create/bind the recorder around command dispatch, finalize before diagnostics, attach artifacts, and convert recorder finalization failures into non-zero CLI errors.

- [x] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
uv run pytest tests/test_cli_json_output.py -q
```

Expected: CLI lifecycle tests pass.

---

### Task 5: Full Verification

**Files:**
- All touched files.

- [x] **Step 1: Run type checking**

Run:

```bash
uv run basedpyright
```

Expected: `0 errors, 0 warnings, 0 notes`.

- [x] **Step 2: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass.

- [x] **Step 3: Run diff check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [x] **Step 4: Completion audit**

Compare the implementation against every explicit requirement in `docs/superpowers/specs/2026-06-07-debug-llm-messages-design.md`, then summarize evidence before marking the goal complete.
