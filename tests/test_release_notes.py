"""Release 正文提取脚本测试。"""

from pathlib import Path

import pytest

from scripts.extract_release_notes import (
    ReleaseNotesOptions,
    extract_release_notes_section,
    write_release_notes,
)


def test_extract_release_notes_section_reads_matching_tag() -> None:
    """发布说明来自 CHANGELOG 中指定 tag 的完整版本段落。"""
    changelog_text = """# 更新日志

## v0.1.10 - 2026-06-01

### 功能变化

- 具体变化。

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


def test_write_release_notes_creates_parent_directory(tmp_path: Path) -> None:
    """写出 Release 正文时自动创建输出目录。"""
    changelog_path = tmp_path / "CHANGELOG.md"
    output_path = tmp_path / "dist" / "release-notes.md"
    _ = changelog_path.write_text(
        "# 更新日志\n\n## v0.1.10 - 2026-06-01\n\n- 具体变化。\n",
        encoding="utf-8",
    )

    write_release_notes(
        ReleaseNotesOptions(
            tag="v0.1.10",
            changelog_path=changelog_path,
            output_path=output_path,
        )
    )

    assert output_path.read_text(encoding="utf-8") == "## v0.1.10 - 2026-06-01\n\n- 具体变化。\n"
