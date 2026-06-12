# Full Pytest Suite Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore full pytest as the local and GitHub Actions Python test gate while reducing local full-suite time to 60 seconds or less and GitHub full pytest step time to 5 minutes or less.

**Architecture:** Keep the test suite semantically unchanged and make execution parallel with `pytest-xdist`. Limit Rust/Rayon thread use per pytest worker with `ATT_MZ_RUST_THREADS=1`, restore release full pytest, add regular CI, and align `AGENTS.md` plus wiki documentation with the current full-suite contract. Do not add tests for this test-infrastructure change; verification is the real full pytest run and CI duration evidence.

**Tech Stack:** Python 3.14, uv dependency groups, pytest, pytest-xdist, GitHub Actions on `windows-latest`, Rust/PyO3 native extension, PowerShell.

---

## File Structure

- Modify `pyproject.toml`: add `pytest-xdist` to the dev dependency group.
- Modify `uv.lock`: lock `pytest-xdist` and its transitive dependency `execnet` through `uv add --dev pytest-xdist`.
- Modify `.github/workflows/release.yml`: replace the temporary release-path pytest subset with full parallel pytest.
- Create `.github/workflows/ci.yml`: run Python type checking and full parallel pytest on pull requests and normal pushes.
- Modify `AGENTS.md`: document the current full pytest command, thread limit, and ban on using test subsets as the Python business-test gate.
- Modify `docs/wiki/development/release-and-tests.md`: align release and CI test documentation with workflow reality.
- Do not create new test files. This task changes how the existing full test suite runs; adding meta-tests would create a test-for-tests loop.

### Task 1: Add pytest-xdist Dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Add the dev dependency with uv**

Run:

```powershell
uv add --dev pytest-xdist
```

Expected:

- `pyproject.toml` dev dependency group includes a `pytest-xdist` entry.
- `uv.lock` includes packages for `pytest-xdist` and `execnet`.
- Existing runtime dependencies remain unchanged except for lock metadata required by uv.

- [ ] **Step 2: Confirm dependency lock state**

Run:

```powershell
rg -n "pytest-xdist|execnet" pyproject.toml uv.lock
```

Expected:

- The output includes one `pyproject.toml` match containing `"pytest-xdist>=`.
- The output includes one `uv.lock` package header `name = "execnet"`.
- The output includes one `uv.lock` package header `name = "pytest-xdist"`.

The exact resolved version comes from uv and must remain unchanged after Step 1.

- [ ] **Step 3: Commit the dependency change**

Run:

```powershell
git add pyproject.toml uv.lock
git diff --cached --name-only
git commit -m "build: 添加 pytest 并行依赖"
```

Expected staged files:

```text
pyproject.toml
uv.lock
```

Do not stage `rust/src/native_core/scope_index/storage.rs`; it is an existing unrelated worktree change.

### Task 2: Restore Full Pytest in Release Workflow

**Files:**
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Replace the temporary pytest subset step**

In `.github/workflows/release.yml`, replace the current step named `Release path tests` with this exact step:

```yaml
      - name: Full Python tests
        shell: pwsh
        env:
          ATT_MZ_RUST_THREADS: "1"
        run: uv run pytest -q -n 8 --durations=30 --durations-min=0.5
```

Expected:

- The release workflow runs full pytest without positional test file arguments.
- The step name no longer says `Release path tests`.
- Rust fmt, clippy, Rust test, build, upload, and publish steps stay unchanged.

- [ ] **Step 2: Confirm the release workflow no longer contains the subset command**

Run:

```powershell
rg -n "Release path tests|test_release_notes.py|test_release_package_layout.py|Full Python tests|pytest -q -n 8" .github/workflows/release.yml
```

Expected:

- The output includes `.github/workflows/release.yml` with `- name: Full Python tests`.
- The output includes `.github/workflows/release.yml` with `run: uv run pytest -q -n 8 --durations=30 --durations-min=0.5`.
- There are no matches for `Release path tests`, `test_release_notes.py`, or `test_release_package_layout.py`.

- [ ] **Step 3: Commit the release workflow change**

Run:

```powershell
git add .github/workflows/release.yml
git diff --cached --name-only
git commit -m "ci: 恢复发布全量 pytest"
```

Expected staged file:

```text
.github/workflows/release.yml
```

### Task 3: Add Regular Python CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the CI workflow**

Create `.github/workflows/ci.yml` with this content:

```yaml
name: ci

on:
  pull_request:
  push:
    branches:
      - "**"
    tags-ignore:
      - "v*"

permissions:
  contents: read

jobs:
  python:
    name: Python validation
    runs-on: windows-latest
    timeout-minutes: 15
    env:
      ATT_MZ_RUST_THREADS: "1"

    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Set up uv
        uses: astral-sh/setup-uv@v8.1.0
        with:
          enable-cache: true

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Install project dependencies
        shell: pwsh
        run: uv sync --locked --dev

      - name: Type check
        shell: pwsh
        run: uv run basedpyright

      - name: Full Python tests
        shell: pwsh
        run: uv run pytest -q -n 8 --durations=30 --durations-min=0.5
```

Expected:

- Pull requests and ordinary branch pushes run Python validation.
- Tag pushes matching `v*` are left to `release.yml`.
- Rust toolchain is available before `uv sync --locked --dev`, matching the release workflow setup order.
- The regular CI does not run Rust fmt, clippy, or Rust test in this phase.

- [ ] **Step 2: Confirm CI workflow content**

Run:

```powershell
rg -n "name: ci|pull_request|tags-ignore|ATT_MZ_RUST_THREADS|basedpyright|pytest -q -n 8" .github/workflows/ci.yml
```

Expected:

- The output includes `.github/workflows/ci.yml:1:name: ci`.
- The output includes `pull_request:`.
- The output includes `tags-ignore:`.
- The output includes `ATT_MZ_RUST_THREADS: "1"`.
- The output includes `run: uv run basedpyright`.
- The output includes `run: uv run pytest -q -n 8 --durations=30 --durations-min=0.5`.

- [ ] **Step 3: Commit the CI workflow**

Run:

```powershell
git add .github/workflows/ci.yml
git diff --cached --name-only
git commit -m "ci: 添加全量 pytest 常规验证"
```

Expected staged file:

```text
.github/workflows/ci.yml
```

### Task 4: Update Project Rules and Wiki

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/wiki/development/release-and-tests.md`

- [ ] **Step 1: Update `AGENTS.md` validation rules**

In `AGENTS.md` section `## 7. 验证与交付`, replace the first bullet with this text:

```markdown
- 涉及 Python/Rust 源码、测试、schema、构建流程、发行流程或可执行契约的项目交付前，必须执行 `uv run basedpyright` 和全量 Python 业务测试，保持 0 warning、0 error、0 failed。当前全量 pytest 推荐命令为先设置 `$env:ATT_MZ_RUST_THREADS = "1"`，再执行 `uv run pytest -q -n 8 --durations=30 --durations-min=0.5`；若实测调整 worker 数，交付说明必须写明最终 worker 数、总耗时和最慢测试列表。
```

Immediately after that bullet, insert this new bullet:

```markdown
- 测试子集、`-k` 排除、跳过慢测试或 release path 子集不得替代全量 Python 业务测试交付红线；只有纯文档、Skill 文案、README 或发布说明等不触及源码和可执行契约的改动，才按下方纯文档规则缩小验证范围。
```

Expected:

- The existing pure documentation rule remains in place.
- `AGENTS.md` now gives the current full pytest command and thread limit.
- The file no longer leaves room for a release-path pytest subset to replace the Python business-test gate.

- [ ] **Step 2: Update release-and-tests wiki failure strategy**

In `docs/wiki/development/release-and-tests.md`, replace this sentence:

```markdown
- 发布工作流先执行 `uv run basedpyright`、`uv run pytest`、`cargo fmt --manifest-path rust/Cargo.toml -- --check`、`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings` 和 `cargo test --manifest-path rust/Cargo.toml`，通过后才构建发行包。
```

with this sentence:

```markdown
- 发布工作流先执行 `uv run basedpyright`、设置 `ATT_MZ_RUST_THREADS=1` 后执行 `uv run pytest -q -n 8 --durations=30 --durations-min=0.5`、`cargo fmt --manifest-path rust/Cargo.toml -- --check`、`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings` 和 `cargo test --manifest-path rust/Cargo.toml`，通过后才构建发行包。
```

- [ ] **Step 3: Update release-and-tests wiki test coverage bullets**

In `docs/wiki/development/release-and-tests.md` section `## 测试覆盖`, replace these two bullets:

```markdown
- `uv run basedpyright` 是 Python 静态类型交付红线。
- `uv run pytest` 是 Python 业务测试交付红线。
```

with these bullets:

```markdown
- `uv run basedpyright` 是 Python 静态类型交付红线。
- 设置 `ATT_MZ_RUST_THREADS=1` 后执行 `uv run pytest -q -n 8 --durations=30 --durations-min=0.5` 是当前 Python 业务测试交付红线；测试子集不能替代全量 pytest。
- 常规 CI 在 pull request 和普通 push 阶段执行 Python 静态类型检查和全量 pytest，发布工作流在构建发行包前再次执行同一全量 pytest 门禁。
```

Expected:

- Wiki describes current workflow behavior.
- Wiki does not preserve the temporary release-path subset as a current gate.

- [ ] **Step 4: Confirm documentation alignment**

Run:

```powershell
rg -n "pytest -q -n 8|测试子集|Release path tests|uv run pytest` 是 Python 业务测试交付红线" AGENTS.md docs/wiki/development/release-and-tests.md .github/workflows
```

Expected:

- `pytest -q -n 8` appears in `AGENTS.md`, `docs/wiki/development/release-and-tests.md`, `.github/workflows/release.yml`, and `.github/workflows/ci.yml`.
- `测试子集` appears in `AGENTS.md` and wiki only as a prohibition.
- `Release path tests` has no matches.
- The old exact phrase ``uv run pytest` 是 Python 业务测试交付红线` has no matches.

- [ ] **Step 5: Commit rules and wiki updates**

Run:

```powershell
git add AGENTS.md docs/wiki/development/release-and-tests.md
git diff --cached --name-only
git commit -m "docs: 收束全量 pytest 验证规范"
```

Expected staged files:

```text
AGENTS.md
docs/wiki/development/release-and-tests.md
```

### Task 5: Local Verification and Worker Count Decision

**Files:**
- No source file changes unless a faster stable worker count is selected.
- May modify: `AGENTS.md`
- May modify: `.github/workflows/release.yml`
- May modify: `.github/workflows/ci.yml`
- May modify: `docs/wiki/development/release-and-tests.md`

- [ ] **Step 1: Run type checking**

Run:

```powershell
uv run basedpyright
```

Expected:

```text
0 errors, 0 warnings, 0 informations
```

If basedpyright output format differs, the pass condition is still 0 errors and 0 warnings.

- [ ] **Step 2: Run full pytest with the baseline worker count**

Run:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q -n 8 --durations=30 --durations-min=0.5
```

Expected:

- All collected tests pass.
- No business tests are skipped because of this change.
- Total pytest wall time is 60 seconds or less on the local development machine.

- [ ] **Step 3: If the baseline is slower than 60 seconds, compare exact worker counts**

Run these commands one at a time:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q -n 6 --durations=20 --durations-min=0.5
uv run pytest -q -n 10 --durations=20 --durations-min=0.5
uv run pytest -q -n 12 --durations=20 --durations-min=0.5
uv run pytest -q -n auto --durations=20 --durations-min=0.5
```

Expected:

- Select the fastest run that still passes every test.
- If the selected command is not `-n 8`, update `AGENTS.md`, `.github/workflows/release.yml`, `.github/workflows/ci.yml`, and `docs/wiki/development/release-and-tests.md` to use the selected worker count.
- If no command reaches 60 seconds locally, do not claim completion; record the fastest run and continue to Task 7.

- [ ] **Step 4: Commit worker count changes if the selected count changed**

Only run this step if Step 3 selected a worker count other than 8.

Run:

```powershell
git add AGENTS.md .github/workflows/release.yml .github/workflows/ci.yml docs/wiki/development/release-and-tests.md
git diff --cached --name-only
git commit -m "test: 调整全量 pytest 并行度"
```

Expected staged files are exactly the files whose worker count changed.

### Task 6: GitHub CI Verification

**Files:**
- No local source file changes.

- [ ] **Step 1: Push the branch**

Run:

```powershell
git status --short
git branch --show-current
git push
```

Expected:

- `git status --short` shows no unstaged or staged changes from this plan.
- The existing unrelated `rust/src/native_core/scope_index/storage.rs` change must either remain intentionally uncommitted or be handled by its owner before push.
- Push succeeds for the current branch.

- [ ] **Step 2: Inspect the regular CI run**

Run:

```powershell
gh run list --workflow ci.yml --limit 5
gh run watch --exit-status
```

Expected:

- The `ci` workflow runs on the pushed branch.
- The `Python validation` job passes.
- The `Full Python tests` step runs full pytest without file arguments.
- The `Full Python tests` step duration is 5 minutes or less.

- [ ] **Step 3: Inspect release workflow configuration without publishing**

Run:

```powershell
rg -n "Full Python tests|pytest -q -n|Release path tests|test_release_notes.py" .github/workflows/release.yml
```

Expected:

- `Full Python tests` is present.
- The final selected `pytest -q -n ...` command is present.
- `Release path tests` and release-path test file arguments are absent.

Do not trigger `release.yml` only to test this change, because the workflow creates release artifacts and may publish a GitHub Release. The restored release workflow will run on the next real tag or explicit release dispatch.

- [ ] **Step 4: If GitHub full pytest exceeds 5 minutes, update worker count once**

If the regular CI full pytest step exceeds 5 minutes, change both workflow files to `-n 6` and keep `ATT_MZ_RUST_THREADS=1`.

Run after editing:

```powershell
git add .github/workflows/release.yml .github/workflows/ci.yml AGENTS.md docs/wiki/development/release-and-tests.md
git commit -m "ci: 调整 GitHub pytest 并行度"
git push
gh run watch --exit-status
```

Expected:

- Full pytest still passes.
- GitHub full pytest step is 5 minutes or less.
- If `-n 6` still exceeds 5 minutes, continue to Task 7 rather than restoring a test subset.

### Task 7: Second-Stage Trigger

**Files:**
- No immediate source file changes in this task.

- [ ] **Step 1: Decide whether fixture snapshot work is required**

Run this decision after Task 5 and Task 6:

```text
If local full pytest is 60 seconds or less and GitHub full pytest is 5 minutes or less, stop here and deliver.
If local full pytest is slower than 60 seconds or GitHub full pytest is slower than 5 minutes after one worker-count adjustment, do not claim completion.
```

Expected:

- If both targets pass, report the final local pytest duration, GitHub pytest duration, worker count, and `ATT_MZ_RUST_THREADS=1`.
- If either target fails, write a separate worker-level fixture snapshot implementation plan before changing fixtures.

- [ ] **Step 2: Preserve the no-subset rule**

If Task 7 is triggered, keep these facts true:

```text
The release workflow still runs full pytest.
The regular CI still runs full pytest.
No slow tests are skipped.
No -k expression is used.
No release path subset replaces full pytest.
```

Expected:

- The project remains safer but slower until fixture snapshot work is explicitly planned and implemented.
- There is no rollback to the temporary subset gate.

## Final Verification Checklist

- [ ] `uv run basedpyright` passes with 0 errors and 0 warnings.
- [ ] Full local pytest passes with the final command and selected worker count.
- [ ] Local full pytest duration is 60 seconds or less, or Task 7 has been triggered with evidence.
- [ ] Regular GitHub CI full pytest passes.
- [ ] GitHub full pytest step duration is 5 minutes or less, or Task 7 has been triggered with evidence.
- [ ] `release.yml` contains full pytest and no release-path subset.
- [ ] `AGENTS.md`, `release.yml`, `ci.yml`, and wiki use the same pytest command and thread limit.
- [ ] No new test files were added for this test-infrastructure change.
- [ ] The unrelated `rust/src/native_core/scope_index/storage.rs` worktree change was not staged or committed by this plan.
