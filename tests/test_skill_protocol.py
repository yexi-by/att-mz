"""阶段 0 Skill、README 和 CLI 协议护栏。"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
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
CURRENT_DOC_PATHS = (
    ROOT / "README.md",
    *sorted((ROOT / "docs" / "wiki").rglob("*.md")),
    *sorted((ROOT / "docs" / "guides").rglob("*.md")),
    *sorted((ROOT / "docs" / "guides").rglob("*.html")),
    PROTOCOL_DIR / "workflow.toml",
    PROTOCOL_DIR / "templates" / "SKILL.md.in",
    *sorted((PROTOCOL_DIR / "templates" / "references").glob("*.md.in")),
    DEV_SKILL_DIR / "SKILL.md",
    RELEASE_SKILL_DIR / "SKILL.md",
    *sorted((DEV_SKILL_DIR / "references").glob("*.md")),
    *sorted((RELEASE_SKILL_DIR / "references").glob("*.md")),
)
PUBLIC_DOC_PATHS = (
    *CURRENT_DOC_PATHS,
    ROOT / "CHANGELOG.md",
)
COMMAND_LINE_PATTERNS = (
    re.compile(r"uv\s+run\s+python\s+main\.py\s+([a-z][a-z0-9-]+)"),
    re.compile(r"(?:\.\\att-mz\.exe|att-mz\.exe)\s+([a-z][a-z0-9-]+)"),
)
REAL_LOCAL_PATH_PATTERNS = (
    re.compile(r"\b[A-Za-z]:[\\/][^\s`>)]*"),
    re.compile(r"(?i)(?:^|[\\/])Users[\\/][^\s`>)]*"),
    re.compile(r"(?i)(?:^|[\\/])Documents and Settings[\\/][^\s`>)]*"),
    re.compile(r"(?i)/(?:Users|home)/[^\s`>)]*"),
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


def test_public_docs_examples_do_not_expose_real_local_paths() -> None:
    """公开文档和 Skill 示例只能使用占位符路径，不暴露具体本地目录。"""
    for path in PUBLIC_DOC_PATHS:
        text = _read_text(path)
        matches = [
            match.group(0)
            for pattern in REAL_LOCAL_PATH_PATTERNS
            for match in pattern.finditer(text)
            if not match.group(0).startswith("<")
        ]
        assert not matches, f"{path.relative_to(ROOT)} 含具体本地目录示例: {matches}"


def test_current_text_index_and_workspace_recovery_entries_are_documented() -> None:
    """README 与 Skill CLI 契约必须说明当前可执行恢复入口。"""
    required_terms = {
        "当前文本索引",
        "rebuild-text-index --game <游戏标题>",
        "当前工作区",
        "prepare-agent-workspace --game <游戏标题> --output-dir <工作区>",
        "rebuild-active-runtime --game <游戏标题>",
    }
    protocol_paths = [
        ROOT / "README.md",
        DEV_SKILL_DIR / "references" / "cli-command-contract.md",
        RELEASE_SKILL_DIR / "references" / "cli-command-contract.md",
    ]

    for path in protocol_paths:
        text = _read_text(path)
        missing_terms = sorted(term for term in required_terms if term not in text)
        assert not missing_terms, f"{path.relative_to(ROOT)} 缺少当前恢复说明: {missing_terms}"


def test_current_docs_describe_text_index_and_invalid_state_recovery() -> None:
    """README 与 Skill 契约必须用当前索引和中性无效状态描述恢复动作。"""
    expected_terms_by_path = {
        ROOT / "README.md": {
            "当前文本索引",
            "索引缺失、过期或范围不一致",
            "当前工作区校验失败",
            "范围信息不可用",
            "缺少可用写回映射",
        },
        DEV_SKILL_DIR / "references" / "cli-command-contract.md": {
            "当前文本索引",
            "不满足当前契约的输入只作为无效输入处理",
            "rebuild-text-index --game <游戏标题>",
            "prepare-agent-workspace --game <游戏标题> --output-dir <工作区>",
            "rebuild-active-runtime --game <游戏标题>",
            "输入路径不属于当前范围时整体失败",
        },
        RELEASE_SKILL_DIR / "references" / "cli-command-contract.md": {
            "当前文本索引",
            "不满足当前契约的输入只作为无效输入处理",
            "rebuild-text-index --game <游戏标题>",
            "prepare-agent-workspace --game <游戏标题> --output-dir <工作区>",
            "rebuild-active-runtime --game <游戏标题>",
            "输入路径不属于当前范围时整体失败",
        },
    }

    for path, expected_terms in expected_terms_by_path.items():
        text = _read_text(path)
        missing_terms = sorted(term for term in expected_terms if term not in text)
        assert not missing_terms, f"{path.relative_to(ROOT)} 缺少当前无效状态恢复说明: {missing_terms}"


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


def test_skill_protocol_defaults_to_autonomous_repair_before_user_choice() -> None:
    """Skill 必须区分真实用户决策和主代理应自动处理的修复项。"""
    required_terms_by_path = {
        PROTOCOL_DIR / "templates" / "SKILL.md.in": {
            "默认自动推进",
            "不把后续可判断的支线处理变成中途选择题",
            "只有需要用户承担额外成本、接受风险或选择完整重译时才询问用户",
        },
        PROTOCOL_DIR / "workflow.toml": {
            "同类失败不下降时已进入诊断和修复流程，而不是让用户代选方案",
            "普通 warning 已由主代理逐项确认；只有接受风险类 warning 需要用户确认",
        },
        PROTOCOL_DIR / "templates" / "references" / "failure-recovery.md.in": {
            "停止无证据续跑并自动进入诊断",
            "不要把“继续重跑、换模型、手动修复、直接写回”做成让用户猜的选择题",
        },
        PROTOCOL_DIR / "templates" / "references" / "agent-review-workflow.md.in": {
            "不要把 `needs_revision`、普通 `warning` 或可由 CLI/报告判断的修复项转成用户选择题",
            "用户确认只用于真实用户决策",
        },
    }

    for path, required_terms in required_terms_by_path.items():
        text = _read_text(path)
        missing_terms = sorted(term for term in required_terms if term not in text)
        assert not missing_terms, f"{path.relative_to(ROOT)} 缺少自动化修复约束: {missing_terms}"


def test_feedback_iteration_documents_rule_cascade_and_overtranslation() -> None:
    """试玩反馈流程必须约束漏翻/多翻根因定位和补规则后的级联检查。"""
    required_terms_by_path = {
        PROTOCOL_DIR / "workflow.toml": {
            "漏翻、多翻或误翻已按根因分类处理",
            "补外部规则后已重新收束占位符并重建当前文本索引",
            "无证据扩大规则",
            "补外部规则后跳过占位符收束",
        },
        PROTOCOL_DIR / "templates" / "references" / "feedback-iteration.md.in": {
            "多翻/过翻",
            "不要为了修一个反馈无证据扩大规则",
            "规则级联",
            "重新运行 `build-placeholder-rules`、`validate-placeholder-rules`、`scan-placeholder-candidates` 和 `import-placeholder-rules`",
            "运行 `rebuild-text-index --game <游戏标题>`",
        },
        PROTOCOL_DIR / "templates" / "references" / "placeholder-rules.md.in": {
            "非标准 data 规则、插件源码规则或 MV 虚拟名字框规则改变后",
            "然后重建当前文本索引",
        },
    }

    for path, required_terms in required_terms_by_path.items():
        text = _read_text(path)
        missing_terms = sorted(term for term in required_terms if term not in text)
        assert not missing_terms, f"{path.relative_to(ROOT)} 缺少试玩反馈规则级联约束: {missing_terms}"


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
    """公开协议文档只保留当前 Agent JSON 入口。"""
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


def test_public_protocol_docs_explain_current_candidate_review_boundaries() -> None:
    """公开协议必须说明 sampled 报告、完整候选和当前规则确认边界。"""
    expected_terms_by_path = {
        DEV_SKILL_DIR / "references" / "cli-command-contract.md": {
            "summary.report_detail_mode=sampled",
            "--output <文件>",
            "完整报告",
        },
        DEV_SKILL_DIR / "references" / "placeholder-rules.md": {
            "summary.uncovered_count",
            "完整候选",
            "重新审查并导入当前规则",
        },
        DEV_SKILL_DIR / "references" / "structured-placeholder-rules.md": {
            "未覆盖候选",
            "剩余风险已确认",
            "重新审查并导入当前规则",
        },
        RELEASE_SKILL_DIR / "references" / "cli-command-contract.md": {
            "summary.report_detail_mode=sampled",
            "--output <文件>",
            "完整报告",
        },
        RELEASE_SKILL_DIR / "references" / "placeholder-rules.md": {
            "summary.uncovered_count",
            "完整候选",
            "重新审查并导入当前规则",
        },
        RELEASE_SKILL_DIR / "references" / "structured-placeholder-rules.md": {
            "未覆盖候选",
            "剩余风险已确认",
            "重新审查并导入当前规则",
        },
    }

    for path, expected_terms in expected_terms_by_path.items():
        text = _read_text(path)
        missing_terms = sorted(term for term in expected_terms if term not in text)
        assert not missing_terms, f"{path.relative_to(ROOT)} 缺少当前候选审查边界: {missing_terms}"


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
        *sorted((DEV_SKILL_DIR / "references").glob("*.md")),
        *sorted((RELEASE_SKILL_DIR / "references").glob("*.md")),
    ]
    for path in protocol_paths:
        text = _read_text(path)
        assert "prepare-translation" not in text, path
