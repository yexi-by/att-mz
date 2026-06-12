# Pytest Fixture Snapshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep full pytest as the Python business-test gate while cutting repeated test setup cost enough for local full pytest to reach 60 seconds or less and GitHub full pytest to reach 5 minutes or less.

**Architecture:** Optimize only test infrastructure. Build the three minimal RPG Maker fixture games once per pytest worker from the existing fixture builders, copy an isolated game directory per test, and route pytest worker logs to worker-local files so xdist workers do not fight over `logs/app.log`. Do not add meta-tests for this change; verification is targeted fixture consumers, `basedpyright`, real full pytest duration, and GitHub Actions step duration.

**Tech Stack:** Python 3.14, pytest, pytest-xdist, PowerShell, GitHub Actions on `windows-latest`.

---

## File Structure

- Modify `tests/conftest.py`: add worker-local Loguru setup, extract minimal game builders, add session-scoped per-worker templates, and keep existing function-scoped fixture names returning isolated copies.
- Modify `app/rmmz/source_snapshot.py`: keep source snapshot behavior identical while copying file contents without preserving metadata that the current contract never reads.
- May modify `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `AGENTS.md`, and `docs/wiki/development/release-and-tests.md`: only if real local or GitHub evidence selects a different final pytest worker/distribution command.
- Do not add production-only shortcuts, test-only branches, skip logic, or alternate facts. The only allowed production change in this plan is content-only file copying for source snapshots, because snapshot validity is already defined by file existence, byte size, and SHA-256 content hash.
- Do not add new test files for this test-infrastructure change.
- Do not stage or commit the existing unrelated `rust/src/native_core/scope_index/storage.rs` change.

### Task 1: Isolate Pytest Worker Logs

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add imports for copy and pytest internals**

Update the top of `tests/conftest.py` so it imports `shutil` and can type the pytest config hook:

```python
import json
import shutil
from pathlib import Path
from typing import cast
```

- [ ] **Step 2: Add worker id and log setup helpers**

Add these helpers after `EXAMPLE_SETTING_PATH`:

```python
def pytest_configure(config: pytest.Config) -> None:
    """让每个 pytest worker 写独立日志文件，避免 xdist 并发争用项目日志。"""
    from app.observability import setup_logger

    log_path = _pytest_worker_log_path(config)
    setup_logger(use_console=False, file_path=log_path, enqueue_file_log=False)


def _pytest_worker_log_path(config: pytest.Config) -> Path:
    """返回当前 pytest 进程专属日志文件路径。"""
    worker_input = getattr(config, "workerinput", None)
    worker_id = "master"
    if isinstance(worker_input, dict):
        raw_worker_id = worker_input.get("workerid")
        if isinstance(raw_worker_id, str) and raw_worker_id:
            worker_id = raw_worker_id
    log_dir = Path.cwd() / ".pytest-cache" / "att-mz-worker-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{worker_id}.log"
```

Expected:

- Tests still control `ATT_MZ_HOME` explicitly where they need runtime path behavior.
- `resolve_log_file_path()` keeps production semantics.
- Parallel pytest no longer rotates or writes one shared `logs/app.log` during test runs.

- [ ] **Step 3: Run a log-related smoke test**

Run:

```powershell
uv run pytest tests/test_observability.py tests/test_runtime_paths.py -q -n 2
```

Expected:

- All selected tests pass.
- No Loguru `PermissionError` appears.

- [ ] **Step 4: Commit log isolation**

Run:

```powershell
git add tests/conftest.py
git diff --cached --name-only
git commit -m "test: 隔离 pytest worker 日志"
```

Expected staged file:

```text
tests/conftest.py
```

### Task 2: Snapshot Minimal Game Directories Per Worker

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add template copy helper**

Add this helper near `write_json`:

```python
def copy_test_game_template(template_root: Path, target_root: Path) -> Path:
    """复制 worker 级游戏模板，保证每个测试拿到可独立修改的目录。"""
    if target_root.exists():
        raise RuntimeError(f"测试游戏目录已存在，不能覆盖: {target_root}")
    _ = shutil.copytree(template_root, target_root, copy_function=shutil.copyfile)
    return target_root
```

- [ ] **Step 2: Extract the MZ fixture builder**

Rename the current body of `minimal_game_dir(tmp_path: Path) -> Path` into:

```python
def build_minimal_game_dir(game_root: Path) -> Path:
    """创建只包含核心流程所需文件的最小 MZ 游戏目录。"""
```

Inside the function, remove the old `game_root = tmp_path / "mini-game"` assignment and keep the existing body unchanged after that line.

- [ ] **Step 3: Add the MZ template and function-scoped copy fixture**

Replace the old `minimal_game_dir` fixture wrapper with:

```python
@pytest.fixture(scope="session")
def minimal_game_dir_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """为当前 pytest worker 创建可复制的最小 MZ 游戏模板。"""
    return build_minimal_game_dir(tmp_path_factory.mktemp("game-templates") / "mini-game")


@pytest.fixture
def minimal_game_dir(tmp_path: Path, minimal_game_dir_template: Path) -> Path:
    """返回当前测试独占的最小 MZ 游戏目录。"""
    return copy_test_game_template(minimal_game_dir_template, tmp_path / "mini-game")
```

- [ ] **Step 4: Extract the MV fixture builder and wrapper**

Apply the same structure to `minimal_mv_game_dir`:

```python
def build_minimal_mv_game_dir(game_root: Path) -> Path:
    """创建外层目录含可执行文件、真实数据位于 www 的最小 MV 游戏目录。"""
```

Add:

```python
@pytest.fixture(scope="session")
def minimal_mv_game_dir_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """为当前 pytest worker 创建可复制的最小 MV 游戏模板。"""
    return build_minimal_mv_game_dir(tmp_path_factory.mktemp("game-templates") / "mini-mv-game")


@pytest.fixture
def minimal_mv_game_dir(tmp_path: Path, minimal_mv_game_dir_template: Path) -> Path:
    """返回当前测试独占的最小 MV 游戏目录。"""
    return copy_test_game_template(minimal_mv_game_dir_template, tmp_path / "mini-mv-game")
```

- [ ] **Step 5: Extract the English fixture builder and wrapper**

Apply the same structure to `minimal_english_game_dir`:

```python
def build_minimal_english_game_dir(game_root: Path) -> Path:
    """创建只含英文玩家可见文本的最小 MZ 游戏目录。"""
```

Add:

```python
@pytest.fixture(scope="session")
def minimal_english_game_dir_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """为当前 pytest worker 创建可复制的英文 MZ 游戏模板。"""
    return build_minimal_english_game_dir(
        tmp_path_factory.mktemp("game-templates") / "english-mini-game"
    )


@pytest.fixture
def minimal_english_game_dir(tmp_path: Path, minimal_english_game_dir_template: Path) -> Path:
    """返回当前测试独占的英文 MZ 游戏目录。"""
    return copy_test_game_template(
        minimal_english_game_dir_template,
        tmp_path / "english-mini-game",
    )
```

Expected:

- Existing fixture names and test behavior remain unchanged.
- Every test receives a private copy under its own `tmp_path`.
- The template is built once per pytest worker process, so xdist keeps isolation without repeating all JSON serialization for every test.

- [ ] **Step 6: Run fixture consumer smoke tests**

Run:

```powershell
uv run pytest tests/test_source_language_probe.py tests/test_rmmz_source_snapshot.py tests/test_persistence.py::test_registry_and_target_session_use_injected_directory tests/test_persistence.py::test_registry_stores_mv_engine_and_content_root -q -n 3
```

Expected:

- All selected tests pass.
- Tests that mutate fixture game files still pass, proving copies are isolated.

- [ ] **Step 7: Run type checking**

Run:

```powershell
uv run basedpyright
```

Expected:

- 0 errors and 0 warnings.

- [ ] **Step 8: Commit fixture snapshots**

Run:

```powershell
git add tests/conftest.py
git diff --cached --name-only
git commit -m "test: 复用 pytest 游戏目录模板"
```

Expected staged file:

```text
tests/conftest.py
```

### Task 3: Use Content-Only Source Snapshot Copies

**Files:**
- Modify: `app/rmmz/source_snapshot.py`

- [ ] **Step 1: Change snapshot copies to content-only copies**

In `create_source_snapshot_for_clean_game`, change the three snapshot copy calls so they avoid metadata preservation:

```python
_ = shutil.copytree(layout.data_dir, layout.data_origin_dir, copy_function=shutil.copyfile)
```

```python
_ = shutil.copyfile(layout.plugins_path, layout.plugins_origin_path)
```

```python
_ = shutil.copyfile(source_path, snapshot_path)
```

Expected:

- Source snapshot files still contain identical bytes.
- `collect_source_snapshot_records` still records byte size and SHA-256 from the copied files.
- Production code still rejects dirty game directories with pre-existing snapshot files.

- [ ] **Step 2: Run source snapshot contract tests**

Run:

```powershell
uv run pytest tests/test_rmmz_source_snapshot.py tests/test_game_reset.py -q -n 3
```

Expected:

- All selected tests pass.
- Existing clean-directory and manifest behavior remains unchanged.

- [ ] **Step 3: Commit content-only snapshot copy**

Run:

```powershell
git add app/rmmz/source_snapshot.py docs/superpowers/plans/2026-06-12-pytest-fixture-snapshots.md
git diff --cached --name-only
git commit -m "perf: 简化可信源快照复制"
```

Expected staged files:

```text
app/rmmz/source_snapshot.py
docs/superpowers/plans/2026-06-12-pytest-fixture-snapshots.md
```

### Task 4: Re-select the Full Pytest Command

**Files:**
- May modify: `.github/workflows/ci.yml`
- May modify: `.github/workflows/release.yml`
- May modify: `AGENTS.md`
- May modify: `docs/wiki/development/release-and-tests.md`

- [ ] **Step 1: Run the current documented full pytest command**

Run:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q -n 6 --durations=30 --durations-min=0.5
```

Expected:

- All tests pass.
- No Loguru `PermissionError` appears.
- If total wall time is 60 seconds or less, keep `-n 6`.

- [ ] **Step 2: Compare local alternatives only if needed**

If Step 1 is slower than 60 seconds, run:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q -n 8 --durations=20 --durations-min=0.5
uv run pytest -q -n 12 --durations=20 --durations-min=0.5
uv run pytest -q -n 12 --dist=worksteal --durations=20 --durations-min=0.5
```

Expected:

- Select the fastest command that passes every test and has no worker log errors.
- Do not use `-k`, skip markers, positional test subsets, or release-path subsets.

- [ ] **Step 3: Update command docs and workflows if the selected command changed**

If the final command is not the currently documented command, update all four files so they describe the same full pytest command:

```text
AGENTS.md
.github/workflows/ci.yml
.github/workflows/release.yml
docs/wiki/development/release-and-tests.md
```

Expected:

- The workflow command still has no positional test file arguments.
- `ATT_MZ_RUST_THREADS=1` remains the configured Rust thread cap.
- Documentation says test subsets cannot replace full pytest.

- [ ] **Step 4: Commit command alignment if files changed**

Run only if Step 3 changed files:

```powershell
git add AGENTS.md .github/workflows/ci.yml .github/workflows/release.yml docs/wiki/development/release-and-tests.md
git diff --cached --name-only
git commit -m "test: 更新全量 pytest 最终命令"
```

Expected:

- Only the four command/documentation files are staged.

### Task 5: Local and GitHub Verification

**Files:**
- No source file changes unless verification selects a different full pytest command.

- [ ] **Step 1: Confirm local static checks and full pytest**

Run:

```powershell
uv run basedpyright
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q <final-worker-and-distribution-flags> --durations=30 --durations-min=0.5
```

Expected:

- basedpyright reports 0 errors and 0 warnings.
- Full pytest passes.
- Local full pytest wall time is 60 seconds or less.

- [ ] **Step 2: Push the branch**

Run:

```powershell
git status --short
git push
```

Expected:

- Only the unrelated `rust/src/native_core/scope_index/storage.rs` may remain unstaged.
- Push succeeds.

- [ ] **Step 3: Verify regular GitHub CI**

Run:

```powershell
gh run list --workflow ci.yml --limit 5
gh run watch --exit-status
gh run view <run-id> --json conclusion,status,createdAt,updatedAt,jobs
```

Expected:

- `Python validation` passes.
- `Full Python tests` runs full pytest without file arguments.
- The full pytest step duration is 5 minutes or less.

- [ ] **Step 4: Confirm release workflow remains full pytest**

Run:

```powershell
rg -n "Full Python tests|pytest -q -n|Release path tests|test_release_notes.py|test_release_package_layout.py" .github/workflows/release.yml
```

Expected:

- `Full Python tests` is present.
- The final full pytest command is present.
- `Release path tests`, `test_release_notes.py`, and `test_release_package_layout.py` are absent.

## Final Verification Checklist

- [ ] Production behavior remains equivalent: source snapshot validity still uses file existence, byte size, and SHA-256 content hash.
- [ ] No new test files were added for test infrastructure.
- [ ] `uv run basedpyright` passes with 0 errors and 0 warnings.
- [ ] Full local pytest passes with the final command and is 60 seconds or less.
- [ ] Regular GitHub CI passes and full pytest step is 5 minutes or less.
- [ ] Release workflow still uses full pytest with no release-path subset.
- [ ] `AGENTS.md`, `release.yml`, `ci.yml`, and wiki describe the final command and no-subset rule.
- [ ] The unrelated `rust/src/native_core/scope_index/storage.rs` change remains unstaged.
