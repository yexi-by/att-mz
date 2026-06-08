"""Release 正文提取脚本测试。"""

import re
from pathlib import Path

import pytest

from scripts.extract_release_notes import (
    ReleaseNotesOptions,
    extract_release_notes_section,
    write_release_notes,
)


ROOT = Path(__file__).resolve().parents[1]


def _changelog_section_by_title(changelog_text: str, title: str) -> str:
    """按版本标题返回 CHANGELOG 段落。"""
    pattern = rf"^## {re.escape(title)}\n.+?(?=^## |\Z)"
    match = re.search(pattern, changelog_text, flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"CHANGELOG.md 缺少版本段落: {title}")
    return match.group(0)


def test_current_release_notes_include_text_fact_v2_contract_changes() -> None:
    """Text Fact Contract v2 发布说明必须写明具体契约变化。"""
    changelog_text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    current_section = _changelog_section_by_title(
        changelog_text,
        "未发布 - Text Fact Contract v2 契约冻结",
    )
    required_terms = {
        "Text Fact Contract v2",
        "v2 facts",
        "rebuild-text-index",
        "旧数据库",
        "旧工作区",
        "旧 runtime map",
        "prepare-agent-workspace",
        "rebuild-active-runtime",
        "真实游戏耗时",
        "--debug-timings",
        "scan budget",
    }

    missing_terms = sorted(term for term in required_terms if term not in current_section)

    assert not missing_terms, f"最新 CHANGELOG 段落缺少 v2 契约变化: {missing_terms}"


def test_text_fact_v2_design_keeps_runtime_literal_out_of_current_domains() -> None:
    """当前 v2 fact domain 列表不得把 runtime literal 伪装成翻译事实。"""
    spec_text = (
        ROOT / "docs" / "superpowers" / "specs" / "2026-06-07-text-fact-contract-v2-design.md"
    ).read_text(encoding="utf-8")
    current_domains = spec_text.split("## 非翻译事实边界", 1)[0]
    non_translation_boundary = spec_text.split("## 非翻译事实边界", 1)[1]

    assert "active_runtime_literal" not in current_domains
    assert "Placeholder 候选和 active runtime literal 诊断" in non_translation_boundary
    assert "不属于当前 v2 fact domains" in non_translation_boundary


def test_extract_release_notes_section_reads_matching_tag() -> None:
    """发布说明来自 CHANGELOG 中指定 tag 的完整版本段落。"""
    changelog_text = """# 更新日志

## v0.1.10 - 2026-06-01

### 功能变化

- 具体变化。

### 修复

- 修复导入规则失败后报告不一致的问题。

### 验证

- `uv run basedpyright`
- `uv run pytest`

### 发行包

- GitHub Release 下载 `att-mz-windows-x86_64.zip`。

## v0.1.9 - 2026-05-31

- 旧版本。
"""

    notes = extract_release_notes_section(
        changelog_text=changelog_text,
        tag="v0.1.10",
    )

    assert notes.startswith("## v0.1.10 - 2026-06-01")
    assert "- 具体变化。" in notes
    assert "## v0.1.9" not in notes


def test_extract_release_notes_section_requires_changelog_entry() -> None:
    """找不到 tag 对应版本说明时不能继续发布。"""
    with pytest.raises(ValueError, match="CHANGELOG.md 中找不到发布标签"):
        _ = extract_release_notes_section(
            changelog_text="# 更新日志\n\n## v0.1.9 - 2026-05-31\n",
            tag="v0.1.10",
        )


@pytest.mark.parametrize(
    ("changelog_body", "message"),
    [
        ("", "发布标签没有正文"),
        ("\n\n", "发布标签没有正文"),
        ("\n\n- 例行更新。\n\n### 验证\n\n- `uv run pytest`\n\n### 发行包\n\n- 下载 `att-mz-windows-x86_64.zip`。\n", "发布正文过于空泛"),
        ("\n\n### 功能变化\n\n- 具体变化。\n\n### 发行包\n\n- 下载 `att-mz-windows-x86_64.zip`。\n", "缺少验证命令"),
        ("\n\n### 功能变化\n\n- 具体变化。\n\n### 验证\n\n- `uv run pytest`\n", "缺少发行包下载信息"),
        ("\n\n### 功能变化\n\n-\n\n### 验证\n\n- `uv run pytest`\n\n### 发行包\n\n- 下载 `att-mz-windows-x86_64.zip`。\n", "存在空条目"),
    ],
)
def test_extract_release_notes_section_rejects_weak_release_body(
    changelog_body: str,
    message: str,
) -> None:
    """发布说明必须包含实际内容、验证命令和发行包下载信息。"""
    changelog_text = f"# 更新日志\n\n## v0.1.10 - 2026-06-01{changelog_body}\n"

    with pytest.raises(ValueError, match=message):
        _ = extract_release_notes_section(
            changelog_text=changelog_text,
            tag="v0.1.10",
        )


def test_write_release_notes_creates_parent_directory(tmp_path: Path) -> None:
    """写出 Release 正文时自动创建输出目录。"""
    changelog_path = tmp_path / "CHANGELOG.md"
    output_path = tmp_path / "dist" / "release-notes.md"
    _ = changelog_path.write_text(
        (
            "# 更新日志\n\n"
            "## v0.1.10 - 2026-06-01\n\n"
            "### 功能变化\n\n"
            "- 具体变化。\n\n"
            "### 验证\n\n"
            "- `uv run pytest`\n\n"
            "### 发行包\n\n"
            "- GitHub Release 下载 `att-mz-windows-x86_64.zip`。\n"
        ),
        encoding="utf-8",
    )

    write_release_notes(
        ReleaseNotesOptions(
            tag="v0.1.10",
            changelog_path=changelog_path,
            output_path=output_path,
        )
    )

    assert "## v0.1.10 - 2026-06-01" in output_path.read_text(encoding="utf-8")
