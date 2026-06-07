"""阶段 0 Skill、README 和 CLI 协议护栏。"""

from __future__ import annotations

import subprocess
import sys
import tomllib
import re
from pathlib import Path
from typing import cast

from app.cli import build_parser
from app.cli.parser import parser_command_names


ROOT = Path(__file__).resolve().parents[1]
DEV_SKILL_DIR = ROOT / "skills" / "att-mz"
RELEASE_SKILL_DIR = ROOT / "skills" / "att-mz-release"
PROTOCOL_DIR = ROOT / "skills" / "att-mz-protocol"
GENERATE_PROTOCOL_SCRIPT = ROOT / "scripts" / "generate_skill_protocol.py"
REQUIRED_FLOW_COMMANDS = frozenset(
    {
        "add-game",
        "prepare-agent-workspace",
        "validate-agent-workspace",
        "import-terminology",
        "import-plugin-rules",
        "import-event-command-rules",
        "import-note-tag-rules",
        "import-placeholder-rules",
        "import-structured-placeholder-rules",
        "translate",
        "quality-report",
        "write-back",
        "verify-feedback-text",
    }
)
REQUIRED_AGENT_REVIEW_STAGE_IDS = frozenset(
    {
        "workspace",
        "mv_virtual_namebox",
        "terminology",
        "external_rules",
        "branch_rules",
        "placeholder_closure",
    }
)
REQUIRED_AGENT_REVIEW_AGENT_IDS = frozenset(
    {
        "att_mz_mv_namebox_discoverer",
        "att_mz_mv_namebox_reviewer",
        "att_mz_terminology_reviewer",
        "att_mz_external_rule_reviewer",
        "att_mz_branch_reviewer",
        "att_mz_placeholder_sentinel",
    }
)
REQUIRED_SUBTASK_PACKAGE_STAGE_IDS = frozenset({"workspace", "terminology", "external_rules"})
COMMAND_LINE_PATTERNS = (
    re.compile(r"uv\s+run\s+python\s+main\.py\s+([a-z][a-z0-9-]+)"),
    re.compile(r"(?:\.\\att-mz\.exe|att-mz\.exe)\s+([a-z][a-z0-9-]+)"),
)


def _read_text(path: Path) -> str:
    """读取协议文件文本。"""
    return path.read_text(encoding="utf-8")


def _read_reference_text(skill_dir: Path) -> str:
    """合并 Skill references 目录中的 Markdown 文本。"""
    return "\n".join(
        reference_path.read_text(encoding="utf-8")
        for reference_path in sorted((skill_dir / "references").glob("*.md"))
    )


def _extract_prefixed_command_examples(text: str) -> set[str]:
    """提取带开发版或发行版入口前缀的命令示例。"""
    examples: set[str] = set()
    for pattern in COMMAND_LINE_PATTERNS:
        examples.update(pattern.findall(text))
    return examples


def _read_toml(path: Path) -> dict[str, object]:
    """读取 TOML 协议文件。"""
    return cast(dict[str, object], tomllib.loads(_read_text(path)))


def test_generated_skill_protocol_outputs_are_current() -> None:
    """Skill 和 references 必须由 canonical 协议源生成。"""
    completed = subprocess.run(
        [sys.executable, str(GENERATE_PROTOCOL_SCRIPT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_skill_protocol_workflow_manifest_commands_and_references_are_valid() -> None:
    """workflow.toml 中声明的命令和 reference 必须能落到真实公开契约。"""
    command_names = parser_command_names(build_parser())
    workflow = _read_toml(PROTOCOL_DIR / "workflow.toml")
    stages = cast(list[dict[str, object]], workflow["stages"])
    stage_ids = [cast(str, stage["id"]) for stage in stages]

    assert len(stage_ids) == len(set(stage_ids))
    assert REQUIRED_FLOW_COMMANDS <= {
        command
        for stage in stages
        for command in cast(list[str], stage["commands"])
        if command in REQUIRED_FLOW_COMMANDS
    }
    for stage in stages:
        for command in cast(list[str], stage["commands"]):
            assert command in command_names, f"{stage['id']} 引用了未知命令 {command}"
        for reference in cast(list[str], stage["references"]):
            assert (DEV_SKILL_DIR / "references" / reference).is_file(), reference
            assert reference in _read_text(DEV_SKILL_DIR / "SKILL.md"), reference
            assert reference in _read_text(RELEASE_SKILL_DIR / "SKILL.md"), reference


def test_agent_review_workflow_reference_is_attached_to_analysis_stages() -> None:
    """分析与规则产出阶段必须引用审查型工作流契约。"""
    workflow = _read_toml(PROTOCOL_DIR / "workflow.toml")
    stages = cast(list[dict[str, object]], workflow["stages"])
    stage_by_id = {cast(str, stage["id"]): stage for stage in stages}

    assert REQUIRED_AGENT_REVIEW_STAGE_IDS <= set(stage_by_id)
    for stage_id in REQUIRED_AGENT_REVIEW_STAGE_IDS:
        references = set(cast(list[str], stage_by_id[stage_id]["references"]))
        assert "agent-review-workflow.md" in references, stage_id


def test_subtask_package_mode_reference_is_attached_to_package_stages() -> None:
    """外部协作任务包契约必须挂到会创建或回收任务包的阶段。"""
    workflow = _read_toml(PROTOCOL_DIR / "workflow.toml")
    stages = cast(list[dict[str, object]], workflow["stages"])
    stage_by_id = {cast(str, stage["id"]): stage for stage in stages}

    assert REQUIRED_SUBTASK_PACKAGE_STAGE_IDS <= set(stage_by_id)
    for stage_id in REQUIRED_SUBTASK_PACKAGE_STAGE_IDS:
        references = set(cast(list[str], stage_by_id[stage_id]["references"]))
        assert "subtask-package-mode.md" in references, stage_id

    for skill_dir in (DEV_SKILL_DIR, RELEASE_SKILL_DIR):
        assert "references/subtask-package-mode.md" in _read_text(skill_dir / "SKILL.md")


def test_agent_review_protocol_exposes_auditable_reports_and_gates() -> None:
    """公开 Skill 必须包含审查型工作流的目录、报告字段和门禁词。"""
    required_terms = {
        "agent-scratch/",
        "agent-reports/",
        "review-reports/",
        "review-decisions/",
        "active_discoveries",
        "blocker | warning | info",
        "approved | needs_revision | skipped_by_user | blocked",
        "存在未关闭 `blocker` 时",
        "禁止任何 import、写回、重建、重置、数据库写入或游戏文件写入",
    }
    protocol_paths = [
        DEV_SKILL_DIR / "references" / "agent-review-workflow.md",
        RELEASE_SKILL_DIR / "references" / "agent-review-workflow.md",
    ]

    for path in protocol_paths:
        text = _read_text(path)
        for term in required_terms:
            assert term in text, path


def test_agent_review_subagent_manifest_declares_review_roles_and_schema() -> None:
    """子代理 manifest 必须声明新增审查角色和分级 findings schema。"""
    subagents = _read_toml(PROTOCOL_DIR / "subagents.toml")
    agents = cast(list[dict[str, object]], subagents["agents"])
    agent_by_id = {cast(str, agent["id"]): agent for agent in agents}

    assert REQUIRED_AGENT_REVIEW_AGENT_IDS <= set(agent_by_id)
    for agent_id in REQUIRED_AGENT_REVIEW_AGENT_IDS:
        agent = agent_by_id[agent_id]
        schema = set(cast(list[str], agent["report_schema"]))
        if "reviewer" in agent_id or agent_id in {
            "att_mz_terminology_reviewer",
            "att_mz_external_rule_reviewer",
            "att_mz_branch_reviewer",
            "att_mz_placeholder_sentinel",
        }:
            assert {"findings", "coverage_checks", "anti_overfit_checks", "quality_checks"} <= schema, agent_id

    for worker_id in ("att_mz_term_curator", "att_mz_rule_analyst", "att_mz_branch_analyst"):
        schema = set(cast(list[str], agent_by_id[worker_id]["report_schema"]))
        assert {"active_discoveries", "scripts_written", "cli_commands_run", "outputs_written"} <= schema


def test_generated_skill_entrypoints_are_profile_specific() -> None:
    """开发版和发行版 Skill 只能暴露各自入口，不交叉污染。"""
    dev_protocol = _read_text(DEV_SKILL_DIR / "SKILL.md") + "\n" + _read_reference_text(DEV_SKILL_DIR)
    release_protocol = _read_text(RELEASE_SKILL_DIR / "SKILL.md") + "\n" + _read_reference_text(RELEASE_SKILL_DIR)

    assert "uv run python main.py" in dev_protocol
    assert ".\\att-mz.exe" not in dev_protocol
    assert ".\\att-mz.exe" in release_protocol
    assert "uv run python main.py" not in release_protocol


def test_skill_frontmatter_default_entry_and_references_are_split() -> None:
    """开发版和发行版 Skill 的入口与 references 维持分离。"""
    dev_skill = _read_text(DEV_SKILL_DIR / "SKILL.md")
    release_skill = _read_text(RELEASE_SKILL_DIR / "SKILL.md")
    dev_references = {path.name for path in (DEV_SKILL_DIR / "references").glob("*.md")}
    release_references = {path.name for path in (RELEASE_SKILL_DIR / "references").glob("*.md")}

    assert dev_skill.startswith("---\nname: att-mz\n")
    assert release_skill.startswith("---\nname: att-mz-release\n")
    assert dev_references
    assert dev_references == release_references


def test_skill_and_readme_command_examples_exist_in_parser() -> None:
    """Skill、README 和发行说明中的入口命令示例必须能被 parser 识别。"""
    command_names = parser_command_names(build_parser())
    sources = {
        "dev_skill": _read_text(DEV_SKILL_DIR / "SKILL.md") + "\n" + _read_reference_text(DEV_SKILL_DIR),
        "release_skill": _read_text(RELEASE_SKILL_DIR / "SKILL.md") + "\n" + _read_reference_text(RELEASE_SKILL_DIR),
        "readme": _read_text(ROOT / "README.md"),
    }

    assert REQUIRED_FLOW_COMMANDS <= command_names
    assert REQUIRED_FLOW_COMMANDS <= {name for name in command_names if name in sources["dev_skill"]}
    assert REQUIRED_FLOW_COMMANDS <= {name for name in command_names if name in sources["release_skill"]}
    for label, text in sources.items():
        examples = _extract_prefixed_command_examples(text)
        unknown_examples = examples - command_names
        assert not unknown_examples, f"{label} 含有 parser 不支持的命令示例: {sorted(unknown_examples)}"


def test_removed_agent_mode_flags_are_absent_from_public_protocol_docs() -> None:
    """公开协议文档不再要求旧的 Agent JSON 开关。"""
    protocol_paths = [
        DEV_SKILL_DIR / "SKILL.md",
        RELEASE_SKILL_DIR / "SKILL.md",
        ROOT / "README.md",
        *sorted((DEV_SKILL_DIR / "references").glob("*.md")),
        *sorted((RELEASE_SKILL_DIR / "references").glob("*.md")),
    ]
    for path in protocol_paths:
        text = _read_text(path)
        assert "--agent-mode" not in text, path
        assert "--json" not in text, path


def test_public_protocol_docs_use_current_environment_contract() -> None:
    """公开说明必须使用当前 ATT_MZ 环境变量契约。"""
    protocol_paths = [
        DEV_SKILL_DIR / "references" / "cli-command-contract.md",
        RELEASE_SKILL_DIR / "references" / "cli-command-contract.md",
        ROOT / "README.md",
    ]
    for path in protocol_paths:
        text = _read_text(path)
        assert "ATT_MZ_LLM_BASE_URL" in text, path
        assert "ATT_MZ_LLM_API_KEY" in text, path
        assert "RPG_MAKER_TOOLS_" not in text, path


def test_public_protocol_docs_do_not_promise_legacy_candidate_hash_compatibility() -> None:
    """公开协议不得继续承诺旧版候选样本 hash 会放行当前流程。"""
    protocol_paths = [
        DEV_SKILL_DIR / "references" / "cli-command-contract.md",
        DEV_SKILL_DIR / "references" / "placeholder-rules.md",
        DEV_SKILL_DIR / "references" / "structured-placeholder-rules.md",
        RELEASE_SKILL_DIR / "references" / "cli-command-contract.md",
        RELEASE_SKILL_DIR / "references" / "placeholder-rules.md",
        RELEASE_SKILL_DIR / "references" / "structured-placeholder-rules.md",
    ]
    for path in protocol_paths:
        text = _read_text(path)
        assert "legacy_hash" not in text, path
        assert "前 100 个候选" not in text, path


def test_cli_contract_uses_debug_diagnostics_for_rebuild_text_index_timings() -> None:
    """重建文本索引的性能信息必须指向 debug diagnostics，而不是普通摘要字段。"""
    protocol_paths = [
        DEV_SKILL_DIR / "references" / "cli-command-contract.md",
        RELEASE_SKILL_DIR / "references" / "cli-command-contract.md",
    ]
    removed_summary_fields = (
        "summary.elapsed_ms",
        "summary.stage_timings",
        "summary.native_thread_count",
    )
    required_debug_terms = (
        "--debug --debug-timings",
        "summary.diagnostics",
        "text_index.rebuild",
        "runtime.native_thread_count",
    )
    for path in protocol_paths:
        text = _read_text(path)
        for field in removed_summary_fields:
            assert field not in text, path
        for term in required_debug_terms:
            assert term in text, path


def test_removed_prepare_translation_command_is_absent_from_user_facing_protocol() -> None:
    """面向用户和 Agent 的恢复路径不得再引用已移除的 prepare-translation 命令。"""
    protocol_paths = [
        DEV_SKILL_DIR / "SKILL.md",
        RELEASE_SKILL_DIR / "SKILL.md",
        ROOT / "README.md",
        ROOT / "app" / "agent_toolkit" / "services" / "workspace.py",
        *sorted((DEV_SKILL_DIR / "references").glob("*.md")),
        *sorted((RELEASE_SKILL_DIR / "references").glob("*.md")),
    ]
    for path in protocol_paths:
        text = _read_text(path)
        assert "prepare-translation" not in text, path
