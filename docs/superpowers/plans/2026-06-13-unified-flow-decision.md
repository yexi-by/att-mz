# Unified Flow Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing `doctor` command into a single flow decision entry that tells the Agent whether to continue, what blocks progress, and what command to run next.

**Architecture:** Add a small pure decision reducer in `app/agent_toolkit/flow_decision.py`, then let `doctor --game` feed it existing reports from game checks, `quality-report` with full write-back read-only check, and refreshed translation status. Add manual import check-only mode and shared import impact fields without creating a second command surface.

**Tech Stack:** Python 3.14, async service mixins, Pydantic report models, SQLite persistence, pytest, basedpyright, existing Rust write-back quality gate through current Python adapters.

---

## File Structure

- Create `app/agent_toolkit/flow_decision.py`
  - Pure decision types and reducer.
  - No database, no filesystem, no service calls.
- Modify `app/agent_toolkit/services/doctor.py`
  - Keep existing environment and game checks.
  - Add flow decision assembly for `doctor --game`.
- Modify `app/persistence/sql.py`
  - Add recent translation run query.
- Modify `app/persistence/run_records.py`
  - Add `read_recent_translation_runs(limit: int)`.
- Modify `app/agent_toolkit/services/common.py`
  - Add protocol method for recent translation runs only if needed by type checking.
- Modify `app/agent_toolkit/services/manual_translation.py`
  - Add `check_only` import mode.
- Modify `app/cli/parser.py`
  - Add `import-manual-translations --check-only`.
- Modify `app/cli/commands/translation.py`
  - Pass `check_only` to service.
- Create `app/agent_toolkit/import_impact.py`
  - Shared import impact summary/detail helpers.
- Modify `app/cli/commands/rules.py`
  - Add import impact fields to CLI-wrapped rule imports.
- Modify `app/cli/commands/terminology.py`
  - Add import impact fields to terminology import report.
- Modify rule import service files:
  - `app/agent_toolkit/services/placeholder_rules.py`
  - `app/agent_toolkit/services/rule_validation.py`
  - `app/agent_toolkit/services/nonstandard_data.py`
- Modify Skill protocol templates:
  - `skills/att-mz-protocol/templates/SKILL.md.in`
  - `skills/att-mz-protocol/templates/references/cli-command-contract.md.in`
  - `skills/att-mz-protocol/templates/references/failure-recovery.md.in`
- Generated Skill files are updated by `uv run python scripts/generate_skill_protocol.py --write`.
- Tests:
  - Create `tests/test_flow_decision.py`
  - Create `tests/test_doctor_flow_decision.py`
  - Modify `tests/test_manual_translation_scope.py`
  - Modify `tests/test_rule_import_transactions.py`
  - Modify `tests/test_terminology.py`
  - Modify `tests/test_persistence.py`

## Scope Check

The design touches four connected surfaces: doctor decision, retry evidence, manual import precheck, and import impact summaries. They should stay in one plan because the user-facing value is one coherent Agent flow; splitting would leave the first implementation unable to explain the next step.

## Task 1: Recent Translation Run Reader

**Files:**
- Modify: `app/persistence/sql.py`
- Modify: `app/persistence/run_records.py`
- Test: `tests/test_persistence.py`

- [ ] **Step 1: Write the failing persistence test**

Append this test near the other translation run persistence tests in `tests/test_persistence.py`:

```python
@pytest.mark.asyncio
async def test_read_recent_translation_runs_orders_newest_first(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """最近正文翻译运行必须按最新优先返回，并遵守数量限制。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")

    async with await registry.open_game("テストゲーム") as session:
        first = await session.start_translation_run(
            total_extracted=10,
            pending_count=10,
            deduplicated_count=10,
            batch_count=1,
        )
        second = await session.start_translation_run(
            total_extracted=10,
            pending_count=7,
            deduplicated_count=7,
            batch_count=1,
        )
        third = await session.start_translation_run(
            total_extracted=10,
            pending_count=7,
            deduplicated_count=7,
            batch_count=1,
        )

        recent_runs = await session.read_recent_translation_runs(limit=2)

    assert [record.run_id for record in recent_runs] == [third.run_id, second.run_id]
    assert first.run_id not in {record.run_id for record in recent_runs}
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
uv run pytest tests/test_persistence.py::test_read_recent_translation_runs_orders_newest_first -q
```

Expected: FAIL because `read_recent_translation_runs` does not exist.

- [ ] **Step 3: Add the SQL query**

Add this constant after `SELECT_LATEST_TRANSLATION_RUN` in `app/persistence/sql.py`:

```python
SELECT_RECENT_TRANSLATION_RUNS = f"""
--sql
    SELECT *
    FROM [{TRANSLATION_RUNS_TABLE_NAME}]
    ORDER BY started_at DESC, run_id DESC
    LIMIT ?
;
"""
```

Also add `"SELECT_RECENT_TRANSLATION_RUNS"` to the `__all__` list in the same file.

- [ ] **Step 4: Add the session method**

In `app/persistence/run_records.py`, import `SELECT_RECENT_TRANSLATION_RUNS` from `.sql`, then add this method after `read_latest_translation_run`:

```python
    async def read_recent_translation_runs(self, *, limit: int) -> list[TranslationRunRecord]:
        """读取最近若干轮正文翻译状态，最新运行排在最前。"""
        if limit <= 0:
            return []
        async with self.connection.execute(SELECT_RECENT_TRANSLATION_RUNS, (limit,)) as cursor:
            rows = await cursor.fetchall()
        return [self._decode_translation_run(row) for row in rows]
```

- [ ] **Step 5: Run the persistence test**

Run:

```powershell
uv run pytest tests/test_persistence.py::test_read_recent_translation_runs_orders_newest_first -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/persistence/sql.py app/persistence/run_records.py tests/test_persistence.py
git commit -m "feat: 读取最近翻译运行"
```

## Task 2: Flow Decision Reducer

**Files:**
- Create: `app/agent_toolkit/flow_decision.py`
- Test: `tests/test_flow_decision.py`

- [ ] **Step 1: Write the failing reducer tests**

Create `tests/test_flow_decision.py`:

```python
"""统一流程裁决纯逻辑测试。"""

from app.agent_toolkit.flow_decision import build_flow_decision
from app.agent_toolkit.reports import AgentReport, issue


def _report(
    *,
    errors: list[str] | None = None,
    summary: dict[str, object] | None = None,
    details: dict[str, object] | None = None,
) -> AgentReport:
    return AgentReport.from_parts(
        errors=[issue(code, code) for code in errors or []],
        warnings=[],
        summary=summary or {},
        details=details or {},
    )


def test_ready_to_translate_when_only_current_pending_remains() -> None:
    """当前只剩 pending 时，裁决应指向继续正文翻译。"""
    decision = build_flow_decision(
        base_error_codes=set(),
        base_warning_codes=set(),
        quality_report=_report(
            errors=["coverage_missing_translation"],
            summary={
                "pending_count": 12,
                "quality_error_count": 0,
                "write_back_probe_executed": True,
                "write_back_probe_mode": "rust_write_gate",
            },
        ),
        translation_status=_report(
            summary={
                "pending_count": 12,
                "run_pending_count": 30,
                "success_count": 18,
                "quality_error_count": 0,
            }
        ),
        recent_runs=[
            {"run_id": "run3", "pending_count": 12, "success_count": 18, "quality_error_count": 0},
            {"run_id": "run2", "pending_count": 30, "success_count": 40, "quality_error_count": 1},
        ],
    )

    assert decision.result == "ready_to_translate"
    assert decision.stage == "full_translation"
    assert decision.can_continue is True
    assert decision.next_command == "translate --game <游戏标题>"


def test_should_stop_retrying_when_recent_runs_no_longer_improve() -> None:
    """连续多轮下降很小时，裁决应要求先诊断而不是继续重试。"""
    decision = build_flow_decision(
        base_error_codes=set(),
        base_warning_codes=set(),
        quality_report=_report(
            errors=["translation_quality_errors"],
            summary={
                "pending_count": 920,
                "quality_error_count": 920,
                "placeholder_risk_count": 734,
                "text_structure_count": 55,
                "write_back_probe_executed": True,
                "write_back_probe_mode": "rust_write_gate",
            },
            details={"error_type_counts": {"placeholder_risk": 734, "text_structure": 55}},
        ),
        translation_status=_report(summary={"pending_count": 920, "success_count": 33, "quality_error_count": 920}),
        recent_runs=[
            {"run_id": "run9", "pending_count": 920, "success_count": 33, "quality_error_count": 920},
            {"run_id": "run8", "pending_count": 953, "success_count": 173, "quality_error_count": 953},
            {"run_id": "run7", "pending_count": 1126, "success_count": 223, "quality_error_count": 1126},
        ],
    )

    assert decision.result == "should_stop_retrying"
    assert decision.stage == "retry_diagnosis"
    assert decision.can_continue is False
    assert decision.blocking_category == "translation_retry"
    assert decision.next_command == "quality-report --game <游戏标题> --include-write-probe"


def test_ready_to_write_back_when_quality_and_probe_are_clean() -> None:
    """没有 pending、质量错误和写回级风险时，裁决应允许请求写文件授权。"""
    decision = build_flow_decision(
        base_error_codes=set(),
        base_warning_codes=set(),
        quality_report=_report(
            summary={
                "pending_count": 0,
                "quality_error_count": 0,
                "placeholder_risk_count": 0,
                "text_structure_count": 0,
                "write_back_protocol_count": 0,
                "write_back_probe_executed": True,
                "write_back_probe_mode": "rust_write_gate",
            }
        ),
        translation_status=_report(summary={"pending_count": 0, "run_pending_count": 0}),
        recent_runs=[],
    )

    assert decision.result == "ready_to_write_back"
    assert decision.stage == "before_write_back"
    assert decision.can_continue is True
    assert decision.requires_user_authorization is True
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
uv run pytest tests/test_flow_decision.py -q
```

Expected: FAIL because `app.agent_toolkit.flow_decision` does not exist.

- [ ] **Step 3: Implement the reducer**

Create `app/agent_toolkit/flow_decision.py`:

```python
"""统一流程裁决纯逻辑。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.agent_toolkit.reports import AgentReport
from app.rmmz.text_rules import JsonObject, JsonValue

type FlowDecisionResult = Literal[
    "blocked",
    "ready_to_translate",
    "should_stop_retrying",
    "ready_for_manual_fix",
    "ready_to_write_back",
    "needs_runtime_audit",
]
type FlowStage = Literal[
    "environment",
    "prepare_rules",
    "full_translation",
    "retry_diagnosis",
    "manual_fix",
    "before_write_back",
    "runtime_audit",
]
type FlowBlockingCategory = Literal[
    "none",
    "environment",
    "rules",
    "terminology",
    "translation_quality",
    "translation_retry",
    "write_back_fact",
    "runtime",
]

RULE_ERROR_CODES = {
    "plugin_rules",
    "event_command_rules",
    "note_tag_rules",
    "placeholder_rules",
    "structured_placeholder_rules",
    "mv_virtual_namebox_rules",
    "plugin_source_review_incomplete",
    "placeholder_rules_invalid",
    "structured_placeholder_rules_invalid",
    "mv_virtual_namebox_rules_invalid",
}
TERMINOLOGY_ERROR_CODES = {
    "terminology_missing",
    "terminology_empty_translation",
    "terminology_invalid",
}
WRITE_BACK_RISK_CODES = {
    "placeholder_risk",
    "text_structure",
    "write_back_protocol",
    "write_back_gate",
    "coverage_unwritable",
}
QUALITY_ERROR_CODES = {
    "translation_quality_errors",
    "source_residual",
    "overwide_line",
}


@dataclass(frozen=True, slots=True)
class FlowDecision:
    """Agent 下一步流程裁决。"""

    result: FlowDecisionResult
    stage: FlowStage
    can_continue: bool
    blocking_category: FlowBlockingCategory
    reason: str
    next_command: str
    write_back_probe_executed: bool
    write_back_probe_mode: str
    requires_user_authorization: bool = False

    def summary_fields(self) -> JsonObject:
        """转换成 `AgentReport.summary` 的稳定字段。"""
        return {
            "flow_decision": self.result,
            "flow_stage": self.stage,
            "flow_can_continue": self.can_continue,
            "flow_blocking_category": self.blocking_category,
            "flow_reason": self.reason,
            "flow_next_command": self.next_command,
            "flow_write_back_probe_executed": self.write_back_probe_executed,
            "flow_write_back_probe_mode": self.write_back_probe_mode,
            "flow_requires_user_authorization": self.requires_user_authorization,
        }

    def detail_fields(self) -> JsonObject:
        """转换成 `AgentReport.details.flow_decision` 的稳定字段。"""
        return {
            "result": self.result,
            "stage": self.stage,
            "can_continue": self.can_continue,
            "blocking_category": self.blocking_category,
            "reason": self.reason,
            "next_command": self.next_command,
            "write_back_probe_executed": self.write_back_probe_executed,
            "write_back_probe_mode": self.write_back_probe_mode,
            "requires_user_authorization": self.requires_user_authorization,
        }


def build_flow_decision(
    *,
    base_error_codes: set[str],
    base_warning_codes: set[str],
    quality_report: AgentReport | None,
    translation_status: AgentReport | None,
    recent_runs: list[Mapping[str, JsonValue]],
) -> FlowDecision:
    """从已有报告归并出一个 Agent 可执行的流程裁决。"""
    _ = base_warning_codes
    quality_codes = {error.code for error in quality_report.errors} if quality_report is not None else set()
    quality_summary = quality_report.summary if quality_report is not None else {}
    status_summary = translation_status.summary if translation_status is not None else {}
    write_probe_executed = _bool(quality_summary.get("write_back_probe_executed"))
    write_probe_mode = _str(quality_summary.get("write_back_probe_mode"))

    if base_error_codes:
        return FlowDecision(
            result="blocked",
            stage="environment",
            can_continue=False,
            blocking_category="environment",
            reason="环境、配置或目标游戏基础检查没通过",
            next_command="doctor --game <游戏标题> --no-check-llm",
            write_back_probe_executed=write_probe_executed,
            write_back_probe_mode=write_probe_mode,
        )
    if quality_report is None:
        return FlowDecision(
            result="blocked",
            stage="prepare_rules",
            can_continue=False,
            blocking_category="rules",
            reason="缺少完整质量和写回级检查结果",
            next_command="quality-report --game <游戏标题> --include-write-probe",
            write_back_probe_executed=False,
            write_back_probe_mode="not_run",
        )

    if quality_codes & RULE_ERROR_CODES:
        return _blocked("rules", "规则或候选审查没通过", "doctor --game <游戏标题> --no-check-llm", write_probe_executed, write_probe_mode)
    if quality_codes & TERMINOLOGY_ERROR_CODES:
        return _blocked("terminology", "术语表与当前规则或写回需求不一致", "export-terminology --game <游戏标题> --output-dir <输出目录>", write_probe_executed, write_probe_mode)
    if quality_codes & WRITE_BACK_RISK_CODES:
        return _blocked("write_back_fact", "写回级只读检查发现控制符、结构或当前文本事实风险", "quality-report --game <游戏标题> --include-write-probe", write_probe_executed, write_probe_mode)

    pending_count = _int(quality_summary.get("pending_count", status_summary.get("pending_count", 0)))
    quality_error_count = _int(quality_summary.get("quality_error_count", status_summary.get("quality_error_count", 0)))
    if _should_stop_retrying(recent_runs=recent_runs, quality_error_count=quality_error_count):
        return FlowDecision(
            result="should_stop_retrying",
            stage="retry_diagnosis",
            can_continue=False,
            blocking_category="translation_retry",
            reason="最近多轮正文翻译下降很小，继续重试收益低",
            next_command="quality-report --game <游戏标题> --include-write-probe",
            write_back_probe_executed=write_probe_executed,
            write_back_probe_mode=write_probe_mode,
        )
    if quality_error_count > 0 or quality_codes & QUALITY_ERROR_CODES:
        return FlowDecision(
            result="ready_for_manual_fix",
            stage="manual_fix",
            can_continue=True,
            blocking_category="translation_quality",
            reason="剩余质量问题适合导出修复表或待补译表精确处理",
            next_command="export-quality-fix-template --game <游戏标题> --output <输出文件>",
            write_back_probe_executed=write_probe_executed,
            write_back_probe_mode=write_probe_mode,
        )
    if pending_count > 0:
        return FlowDecision(
            result="ready_to_translate",
            stage="full_translation",
            can_continue=True,
            blocking_category="none",
            reason=f"当前还有 {pending_count} 条文本没成功保存译文，可以继续正文翻译",
            next_command="translate --game <游戏标题>",
            write_back_probe_executed=write_probe_executed,
            write_back_probe_mode=write_probe_mode,
        )
    return FlowDecision(
        result="ready_to_write_back",
        stage="before_write_back",
        can_continue=True,
        blocking_category="none",
        reason="当前可写范围没有 pending、质量错误或写回级风险",
        next_command="write-back --game <游戏标题>",
        write_back_probe_executed=write_probe_executed,
        write_back_probe_mode=write_probe_mode,
        requires_user_authorization=True,
    )


def _blocked(
    category: FlowBlockingCategory,
    reason: str,
    next_command: str,
    write_probe_executed: bool,
    write_probe_mode: str,
) -> FlowDecision:
    return FlowDecision(
        result="blocked",
        stage="prepare_rules",
        can_continue=False,
        blocking_category=category,
        reason=reason,
        next_command=next_command,
        write_back_probe_executed=write_probe_executed,
        write_back_probe_mode=write_probe_mode,
    )


def _should_stop_retrying(*, recent_runs: list[Mapping[str, JsonValue]], quality_error_count: int) -> bool:
    if len(recent_runs) < 3 or quality_error_count <= 0:
        return False
    newest = recent_runs[0]
    oldest = recent_runs[min(2, len(recent_runs) - 1)]
    newest_pending = _int(newest.get("pending_count"))
    oldest_pending = _int(oldest.get("pending_count"))
    newest_success = _int(newest.get("success_count"))
    if oldest_pending <= 0:
        return False
    improvement = oldest_pending - newest_pending
    return improvement <= max(10, oldest_pending // 20) and newest_success <= max(10, newest_pending // 20)


def _int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _bool(value: object) -> bool:
    return isinstance(value, bool) and value


def _str(value: object) -> str:
    return value if isinstance(value, str) else ""
```

- [ ] **Step 4: Run reducer tests**

Run:

```powershell
uv run pytest tests/test_flow_decision.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/agent_toolkit/flow_decision.py tests/test_flow_decision.py
git commit -m "feat: 添加统一流程裁决模型"
```

## Task 3: Wire Flow Decision Into Doctor

**Files:**
- Modify: `app/agent_toolkit/services/doctor.py`
- Modify: `app/agent_toolkit/services/common.py`
- Test: `tests/test_doctor_flow_decision.py`

- [ ] **Step 1: Write the failing service integration test**

Create `tests/test_doctor_flow_decision.py`:

```python
"""doctor 统一流程裁决测试。"""

from pathlib import Path

import pytest

from app.agent_toolkit import AgentToolkitService
from app.persistence import GameRegistry

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


@pytest.mark.asyncio
async def test_doctor_game_reports_flow_decision_and_runs_write_probe(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """doctor --game 必须给出统一流程裁决，并默认执行写回级只读检查。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).doctor(game_title="テストゲーム", check_llm=False)

    assert "flow_decision" in report.summary
    assert "flow_stage" in report.summary
    assert "flow_next_command" in report.summary
    assert report.summary["flow_write_back_probe_executed"] is True
    assert report.summary["flow_write_back_probe_mode"] == "rust_write_gate"
    assert "flow_decision" in report.details
    assert report.details["flow_reports"]["quality"]["summary"]["write_back_probe_executed"] is True
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
uv run pytest tests/test_doctor_flow_decision.py::test_doctor_game_reports_flow_decision_and_runs_write_probe -q
```

Expected: FAIL because `doctor` has no `flow_decision` fields.

- [ ] **Step 3: Import reducer and add recent run conversion**

At the top of `app/agent_toolkit/services/doctor.py`, add:

```python
from app.agent_toolkit.flow_decision import build_flow_decision
from app.rmmz.text_rules import JsonValue
```

Add this helper near the bottom of the file:

```python
def _recent_run_payloads(records: object) -> list[dict[str, JsonValue]]:
    """把最近运行记录转成流程裁决只读输入。"""
    if not isinstance(records, list):
        return []
    payloads: list[dict[str, JsonValue]] = []
    for record in records:
        run_id = getattr(record, "run_id", "")
        pending_count = getattr(record, "pending_count", 0)
        success_count = getattr(record, "success_count", 0)
        quality_error_count = getattr(record, "quality_error_count", 0)
        if not isinstance(run_id, str):
            run_id = ""
        if not isinstance(pending_count, int) or isinstance(pending_count, bool):
            pending_count = 0
        if not isinstance(success_count, int) or isinstance(success_count, bool):
            success_count = 0
        if not isinstance(quality_error_count, int) or isinstance(quality_error_count, bool):
            quality_error_count = 0
        payloads.append(
            {
                "run_id": run_id,
                "pending_count": pending_count,
                "success_count": success_count,
                "quality_error_count": quality_error_count,
            }
        )
    return payloads
```

- [ ] **Step 4: Add protocol methods required by doctor**

In `app/agent_toolkit/services/common.py`, add these methods to `AgentServiceContext` after `rebuild_text_index`:

```python
    async def quality_report(
        self,
        *,
        game_title: str,
        setting_overrides: SettingOverrides | None = None,
        callbacks: QualityProgressCallbacks | None = None,
        include_write_probe: bool = False,
    ) -> AgentReport:
        """生成目标游戏当前翻译状态和质量风险报告。"""
        ...

    async def translation_status(
        self,
        *,
        game_title: str,
        refresh_scope: bool = False,
        callbacks: QualityProgressCallbacks | None = None,
    ) -> AgentReport:
        """读取最新正文翻译运行状态。"""
        ...
```

- [ ] **Step 5: Add flow assembly to `doctor`**

In `DoctorAgentMixin.doctor`, after `_check_game(...)` returns and before `AgentReport.from_parts(...)`, add:

```python
        if game_title is not None:
            quality_report: AgentReport | None = None
            translation_status_report: AgentReport | None = None
            recent_run_payloads: list[dict[str, JsonValue]] = []
            if not errors:
                quality_report = await self.quality_report(
                    game_title=game_title,
                    include_write_probe=True,
                )
                translation_status_report = await self.translation_status(
                    game_title=game_title,
                    refresh_scope=True,
                )
                async with await self.game_registry.open_game(game_title) as session:
                    recent_run_payloads = _recent_run_payloads(
                        await session.read_recent_translation_runs(limit=5)
                    )
            decision = build_flow_decision(
                base_error_codes={item.code for item in errors},
                base_warning_codes={item.code for item in warnings},
                quality_report=quality_report,
                translation_status=translation_status_report,
                recent_runs=recent_run_payloads,
            )
            summary.update(decision.summary_fields())
            details["flow_decision"] = decision.detail_fields()
            details["flow_reports"] = {
                "quality": quality_report.model_dump(mode="json") if quality_report is not None else None,
                "translation_status": (
                    translation_status_report.model_dump(mode="json")
                    if translation_status_report is not None
                    else None
                ),
                "recent_runs": recent_run_payloads,
            }
            if not decision.can_continue and not errors:
                errors.append(issue("flow_blocked", decision.reason))
```

Keep the existing `AgentReport.from_parts(...)` call unchanged after this block.

- [ ] **Step 6: Run the doctor test**

Run:

```powershell
uv run pytest tests/test_doctor_flow_decision.py::test_doctor_game_reports_flow_decision_and_runs_write_probe -q
```

Expected: PASS.

- [ ] **Step 7: Run reducer and doctor tests together**

Run:

```powershell
uv run pytest tests/test_flow_decision.py tests/test_doctor_flow_decision.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add app/agent_toolkit/services/doctor.py app/agent_toolkit/services/common.py tests/test_doctor_flow_decision.py
git commit -m "feat: doctor 输出统一流程裁决"
```

## Task 4: Manual Translation Check-Only Mode

**Files:**
- Modify: `app/cli/parser.py`
- Modify: `app/cli/commands/translation.py`
- Modify: `app/agent_toolkit/services/manual_translation.py`
- Test: `tests/test_manual_translation_scope.py`

- [ ] **Step 1: Write the failing check-only test**

Append this test to `tests/test_manual_translation_scope.py`:

```python
@pytest.mark.asyncio
async def test_manual_import_check_only_validates_without_saving(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动译文保存前校验通过时也不得写入数据库。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"

    export_path = tmp_path / "pending.json"
    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=export_path,
        limit=1,
    )
    assert export_report.status in {"ok", "warning"}
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    location_path = next(iter(payload))
    payload[location_path]["translation_lines"] = ["保存前校验译文"]
    _ = export_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=export_path,
        check_only=True,
    )

    assert report.status == "ok"
    assert report.summary["mode"] == "check_only"
    assert report.summary["imported_count"] == 0
    assert report.summary["would_import_count"] == 1
    async with await registry.open_game("テストゲーム") as session:
        saved_items = await session.read_translated_items()
    assert saved_items == []
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
uv run pytest tests/test_manual_translation_scope.py::test_manual_import_check_only_validates_without_saving -q
```

Expected: FAIL because `check_only` is not accepted.

- [ ] **Step 3: Add CLI argument**

In `app/cli/parser.py`, after `--input` for `import-manual-translations`, add:

```python
    _ = import_manual_parser.add_argument(
        "--check-only",
        action="store_true",
        help="只校验手动译文表，不保存任何译文",
    )
```

- [ ] **Step 4: Pass the argument through the CLI command**

In `app/cli/commands/translation.py`, update the service call:

```python
    report = await service.import_manual_translations(
        game_title=game_title,
        input_path=input_path,
        import_valid=read_bool_arg(args, "import_valid"),
        check_only=read_bool_arg(args, "check_only"),
        report_invalid_path=report_invalid_path,
    )
```

- [ ] **Step 5: Add service parameter and summary fields**

In `app/agent_toolkit/services/manual_translation.py`, change the method signature:

```python
    async def import_manual_translations(
        self: AgentServiceContext,
        *,
        game_title: str,
        input_path: Path,
        import_valid: bool = False,
        check_only: bool = False,
        report_invalid_path: Path | None = None,
    ) -> AgentReport:
```

Inside `import_summary`, add stable mode fields:

```python
                "mode": "check_only" if check_only else "import",
                "would_import_count": 0,
```

Then set `summary["would_import_count"] = imported_count` when `check_only` is true:

```python
            if check_only:
                summary["would_import_count"] = imported_count
                summary["imported_count"] = 0
```

- [ ] **Step 6: Stop before database writes in check-only mode**

After the optional invalid report write block and before `await session.write_translation_items(plan.valid_items)`, add:

```python
            if check_only:
                if plan.errors:
                    return AgentReport.from_parts(
                        errors=plan.errors,
                        warnings=rebuild_warnings,
                        summary=import_summary(
                            imported_count=len(plan.valid_items),
                            error_count=len(plan.errors),
                            invalid_count=len(plan.invalid_items),
                        ),
                        details={"invalid_items": plan.invalid_items},
                    )
                return AgentReport.from_parts(
                    errors=[],
                    warnings=rebuild_warnings,
                    summary=import_summary(imported_count=len(plan.valid_items)),
                    details={},
                )
```

- [ ] **Step 7: Run manual translation tests**

Run:

```powershell
uv run pytest tests/test_manual_translation_scope.py -q
```

Expected: PASS.

- [ ] **Step 8: Run CLI parser contract test**

Run:

```powershell
uv run pytest tests/test_cli_json_output.py::test_parser_commands_have_dispatch_handlers -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add app/cli/parser.py app/cli/commands/translation.py app/agent_toolkit/services/manual_translation.py tests/test_manual_translation_scope.py
git commit -m "feat: 手动译文支持保存前校验"
```

## Task 5: Shared Import Impact Summary

**Files:**
- Create: `app/agent_toolkit/import_impact.py`
- Modify: `app/cli/commands/rules.py`
- Modify: `app/cli/commands/terminology.py`
- Modify: `app/agent_toolkit/services/placeholder_rules.py`
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify: `app/agent_toolkit/services/nonstandard_data.py`
- Test: `tests/test_rule_import_transactions.py`
- Test: `tests/test_terminology.py`

- [ ] **Step 1: Write failing tests for rule import impact**

In `tests/test_rule_import_transactions.py`, extend `test_rule_import_writes_backup_before_commit` with these assertions after the existing summary assertions:

```python
    assert report.summary["impact_requires_doctor"] is True
    assert report.summary["impact_requires_text_index_rebuild"] is True
    assert report.summary["impact_write_back_probe_affected"] is True
    assert report.summary["impact_deleted_translation_count"] == 1
    assert report.details["import_impact"]["deleted_translation_count"] == 1
```

- [ ] **Step 2: Write failing test for terminology impact**

In `tests/test_terminology.py`, extend `test_import_terminology_accepts_cleaned_glossary_from_wrapped_field_terms` after the import summary assertion:

```python
    assert import_summary.imported_entry_count > 0
    assert import_summary.impact_requires_doctor is True
    assert import_summary.impact_write_back_probe_affected is True
```

Then update `TerminologyImportSummary` expectations in this file only after the dataclass is changed.

- [ ] **Step 3: Run the failing tests**

Run:

```powershell
uv run pytest tests/test_rule_import_transactions.py::test_rule_import_writes_backup_before_commit tests/test_terminology.py::test_import_terminology_accepts_cleaned_glossary_from_wrapped_field_terms -q
```

Expected: FAIL because impact fields do not exist.

- [ ] **Step 4: Add shared impact helper**

Create `app/agent_toolkit/import_impact.py`:

```python
"""规则和术语导入后的连锁影响报告字段。"""

from __future__ import annotations

from dataclasses import dataclass

from app.rmmz.text_rules import JsonArray, JsonObject


@dataclass(frozen=True, slots=True)
class ImportImpact:
    """导入命令对后续流程的影响摘要。"""

    requires_doctor: bool
    requires_text_index_rebuild: bool
    write_back_probe_affected: bool
    deleted_translation_count: int = 0
    deleted_translation_backup_path: str = ""
    review_recheck_domains: tuple[str, ...] = ()
    terminology_write_back_affected: bool = False

    def summary_fields(self) -> JsonObject:
        """生成稳定 summary 字段。"""
        review_domains: JsonArray = [domain for domain in self.review_recheck_domains]
        return {
            "impact_requires_doctor": self.requires_doctor,
            "impact_requires_text_index_rebuild": self.requires_text_index_rebuild,
            "impact_write_back_probe_affected": self.write_back_probe_affected,
            "impact_deleted_translation_count": self.deleted_translation_count,
            "impact_deleted_translation_backup_path": self.deleted_translation_backup_path,
            "impact_review_recheck_domains": review_domains,
            "impact_terminology_write_back_affected": self.terminology_write_back_affected,
        }

    def detail_fields(self) -> JsonObject:
        """生成 details.import_impact 字段。"""
        return {
            "requires_doctor": self.requires_doctor,
            "requires_text_index_rebuild": self.requires_text_index_rebuild,
            "write_back_probe_affected": self.write_back_probe_affected,
            "deleted_translation_count": self.deleted_translation_count,
            "deleted_translation_backup_path": self.deleted_translation_backup_path,
            "review_recheck_domains": [domain for domain in self.review_recheck_domains],
            "terminology_write_back_affected": self.terminology_write_back_affected,
        }


def rule_import_impact(
    *,
    deleted_translation_count: int,
    deleted_translation_backup_path: str | None,
    review_recheck_domains: tuple[str, ...] = (),
) -> ImportImpact:
    """规则导入后的默认影响。"""
    return ImportImpact(
        requires_doctor=True,
        requires_text_index_rebuild=True,
        write_back_probe_affected=True,
        deleted_translation_count=deleted_translation_count,
        deleted_translation_backup_path=deleted_translation_backup_path or "",
        review_recheck_domains=review_recheck_domains,
    )


def terminology_import_impact() -> ImportImpact:
    """术语导入后的默认影响。"""
    return ImportImpact(
        requires_doctor=True,
        requires_text_index_rebuild=False,
        write_back_probe_affected=True,
        terminology_write_back_affected=True,
    )
```

- [ ] **Step 5: Add terminology dataclass fields**

In `app/application/summaries.py`, update `TerminologyImportSummary`:

```python
@dataclass(slots=True)
class TerminologyImportSummary:
    """外部字段译名表和正文术语表导入任务摘要。"""

    imported_entry_count: int
    filled_entry_count: int
    glossary_term_count: int
    impact_requires_doctor: bool = True
    impact_write_back_probe_affected: bool = True
```

The defaults keep direct application-layer callers source-compatible.

- [ ] **Step 6: Add terminology CLI impact fields**

In `app/cli/commands/terminology.py`, import:

```python
from app.agent_toolkit.import_impact import terminology_import_impact
```

Before constructing the success report in `run_import_terminology_command`, add:

```python
    impact = terminology_import_impact()
```

Then update the success report:

```python
        summary={
            "game": game_title,
            "input": str(input_path),
            "glossary_input": str(glossary_input_path),
            "imported_entry_count": summary.imported_entry_count,
            "filled_entry_count": summary.filled_entry_count,
            "glossary_term_count": summary.glossary_term_count,
            **impact.summary_fields(),
        },
        details={"import_impact": impact.detail_fields()},
```

- [ ] **Step 7: Add CLI rule impact fields**

In `app/cli/commands/rules.py`, import:

```python
from app.agent_toolkit.import_impact import rule_import_impact
```

In `run_import_plugin_rules_command` and `run_import_event_command_rules_command`, build `impact` after warnings:

```python
    impact = rule_import_impact(
        deleted_translation_count=summary.deleted_translation_items,
        deleted_translation_backup_path=summary.deleted_translation_backup_path,
    )
```

Add `**impact.summary_fields()` to the report summary and merge details:

```python
        details={
            **build_deleted_translation_backup_details(summary.deleted_translation_backup_path),
            "import_impact": impact.detail_fields(),
        },
```

- [ ] **Step 8: Add service rule impact fields**

For AgentToolkitService rule import reports, add the same helper fields:

```python
from app.agent_toolkit.import_impact import rule_import_impact
```

Apply to these exact success report builders:

- `app/agent_toolkit/services/placeholder_rules.py` inside `_placeholder_import_report`.
- `app/agent_toolkit/services/rule_validation.py` in success reports for `import_note_tag_rules`, `import_plugin_source_rules`, `import_source_residual_rules`, and `import_mv_virtual_namebox_rules`.
- `app/agent_toolkit/services/nonstandard_data.py` in `import_nonstandard_data_rules`.

For each success report:

```python
impact = rule_import_impact(
    deleted_translation_count=deleted_translation_items,
    deleted_translation_backup_path=deleted_translation_backup_path,
)
```

If the import method does not delete translations, pass `0` and `None`. Add `**impact.summary_fields()` to `summary` and set `details["import_impact"] = impact.detail_fields()`.

- [ ] **Step 9: Run import impact tests**

Run:

```powershell
uv run pytest tests/test_rule_import_transactions.py::test_rule_import_writes_backup_before_commit tests/test_terminology.py::test_import_terminology_accepts_cleaned_glossary_from_wrapped_field_terms -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add app/agent_toolkit/import_impact.py app/application/summaries.py app/cli/commands/rules.py app/cli/commands/terminology.py app/agent_toolkit/services/placeholder_rules.py app/agent_toolkit/services/rule_validation.py app/agent_toolkit/services/nonstandard_data.py tests/test_rule_import_transactions.py tests/test_terminology.py
git commit -m "feat: 导入命令报告连锁影响"
```

## Task 6: Skill Protocol And User Docs

**Files:**
- Modify: `skills/att-mz-protocol/templates/SKILL.md.in`
- Modify: `skills/att-mz-protocol/templates/references/cli-command-contract.md.in`
- Modify: `skills/att-mz-protocol/templates/references/failure-recovery.md.in`
- Generated:
  - `skills/att-mz/SKILL.md`
  - `skills/att-mz/references/*.md`
  - `skills/att-mz-release/SKILL.md`
  - `skills/att-mz-release/references/*.md`

- [ ] **Step 1: Update canonical CLI command contract**

In `skills/att-mz-protocol/templates/references/cli-command-contract.md.in`, change the `doctor` rows to state:

```markdown
| 统一流程裁决 | `doctor --game <游戏标题> --no-check-llm` | Agent 默认先看 `summary.flow_decision`、`summary.flow_stage`、`summary.flow_next_command`。有目标游戏时会执行完整写回级只读检查，不写游戏文件。 |
```

Also update `import-manual-translations` row:

```markdown
| 保存前校验手动译文 | `import-manual-translations --game <游戏标题> --input <文件> --check-only` | 只检查整包译文是否合法，不保存。通过后再去掉 `--check-only` 正式导入。 |
```

- [ ] **Step 2: Update failure recovery template**

In `skills/att-mz-protocol/templates/references/failure-recovery.md.in`, update the retry section so the first bullet is:

```markdown
- 每轮 `translate` 后先运行 `doctor --game <游戏标题> --no-check-llm`；只有 `summary.flow_decision=ready_to_translate` 时继续翻译。
```

Add this line to manual repair:

```markdown
正式导入手动译文前，先运行 `import-manual-translations --game <游戏标题> --input <文件> --check-only`，确认整包译文不会制造新的结构、控制符或写回级问题。
```

- [ ] **Step 3: Update main Skill template**

In `skills/att-mz-protocol/templates/SKILL.md.in`, update the pass criteria for translation and write-back stages to mention:

```markdown
- `doctor --game <游戏标题> --no-check-llm` 给出可继续的 `flow_decision`。
- 写回前 `flow_decision` 必须是 `ready_to_write_back`，真正写文件仍需用户确认。
```

- [ ] **Step 4: Regenerate Skill files**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --write
```

Expected: command exits 0 and updates generated `skills/att-mz*` files.

- [ ] **Step 5: Check generated files are stable**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: PASS with no generated drift.

- [ ] **Step 6: Commit**

```powershell
git add skills/att-mz-protocol/templates/SKILL.md.in skills/att-mz-protocol/templates/references/cli-command-contract.md.in skills/att-mz-protocol/templates/references/failure-recovery.md.in skills/att-mz skills/att-mz-release
git commit -m "docs: 更新统一流程裁决协议"
```

## Task 7: Verification Gate

**Files:**
- No code changes unless verification exposes failures.

- [ ] **Step 1: Run targeted Python tests**

Run:

```powershell
uv run pytest tests/test_flow_decision.py tests/test_doctor_flow_decision.py tests/test_manual_translation_scope.py tests/test_rule_import_transactions.py tests/test_terminology.py tests/test_persistence.py::test_read_recent_translation_runs_orders_newest_first -q
```

Expected: PASS.

- [ ] **Step 2: Run Skill generation check**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: PASS.

- [ ] **Step 3: Run type check**

Run:

```powershell
uv run basedpyright
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 4: Run full Python business tests**

Run:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q -n 12 --dist=load --durations=30 --durations-min=0.5
```

Expected: 0 failed. Record total time and slowest tests in the final delivery.

- [ ] **Step 5: Decide whether Rust checks are required**

If implementation only reuses existing Rust write-back gate through Python and does not modify `rust/`, no Rust command is required. If any `rust/**/*.rs`, `rust/Cargo.toml`, native contract, or write-back gate Rust field is changed, run:

```powershell
Set-Location rust
cargo fmt -- --check
cargo clippy --all-targets -- -D warnings
cargo test
Set-Location ..
```

Expected: all pass.

- [ ] **Step 6: Final commit if verification fixes were needed**

If verification required additional fixes:

Run `git status --short`, then add only the files changed by the verification fix and commit:

```powershell
git status --short
git add app tests skills docs
git commit -m "fix: 收束统一流程裁决验证问题"
```

## Self-Review

- Spec coverage: covered doctor as total entry, full write-back read-only check, retry stop decision, manual precheck, import impact summary, and Skill protocol update.
- No second command: plan upgrades existing `doctor`; it does not add another total entry.
- No runtime human choice: `doctor` gives Agent next command and only marks true write-file/font authorization as user authorization.
- No private sample or local path contract: tests use project fixtures and temporary directories only.
- Python/Rust boundary: first implementation reuses existing Rust write-back gate; Rust changes are conditional, not assumed.
