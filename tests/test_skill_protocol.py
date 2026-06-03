"""阶段 0 Skill、README 和 CLI 协议护栏。"""

from __future__ import annotations

import re
from pathlib import Path

from app.cli import build_parser
from app.cli.parser import parser_command_names


ROOT = Path(__file__).resolve().parents[1]
DEV_SKILL_DIR = ROOT / "skills" / "att-mz"
RELEASE_SKILL_DIR = ROOT / "skills" / "att-mz-release"
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
        ROOT / "docs" / "development" / "release-and-tests.md",
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
        ROOT / "docs" / "advanced-usage.md",
    ]
    for path in protocol_paths:
        text = _read_text(path)
        assert "legacy_hash" not in text, path
        assert "前 100 个候选" not in text, path
