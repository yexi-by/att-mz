"""从更新日志提取指定标签的 GitHub Release 正文。"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANGELOG_PATH = ROOT / "CHANGELOG.md"


@dataclass(frozen=True, slots=True)
class ReleaseNotesOptions:
    """Release 正文提取参数。"""

    tag: str
    changelog_path: Path
    output_path: Path


def parse_args() -> ReleaseNotesOptions:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="从 CHANGELOG.md 提取指定 tag 的发布说明")
    _ = parser.add_argument("--tag", required=True, help="发布标签，例如 v0.1.10")
    _ = parser.add_argument(
        "--changelog",
        default=str(DEFAULT_CHANGELOG_PATH),
        help="更新日志路径，默认读取仓库 CHANGELOG.md",
    )
    _ = parser.add_argument("--output", required=True, help="写出的 Release 正文 markdown 文件")
    namespace = parser.parse_args()
    return ReleaseNotesOptions(
        tag=str(namespace.tag),
        changelog_path=Path(str(namespace.changelog)).resolve(),
        output_path=Path(str(namespace.output)).resolve(),
    )


def extract_release_notes_section(*, changelog_text: str, tag: str) -> str:
    """提取 `CHANGELOG.md` 中指定 tag 的二级标题段落。"""
    normalized_tag = tag.strip()
    if not normalized_tag.startswith("v"):
        raise ValueError("发布标签必须以 v 开头，例如 v0.1.10")

    heading_pattern = re.compile(
        rf"^##\s+{re.escape(normalized_tag)}(?:\s+-\s+.*)?\s*$",
        re.MULTILINE,
    )
    match = heading_pattern.search(changelog_text)
    if match is None:
        raise ValueError(f"CHANGELOG.md 中找不到发布标签: {normalized_tag}")

    next_heading = re.search(r"^##\s+v", changelog_text[match.end():], re.MULTILINE)
    end_index = len(changelog_text) if next_heading is None else match.end() + next_heading.start()
    notes = changelog_text[match.start():end_index].strip()
    if not notes:
        raise ValueError(f"CHANGELOG.md 中发布标签没有正文: {normalized_tag}")
    return notes + "\n"


def write_release_notes(options: ReleaseNotesOptions) -> None:
    """读取更新日志并写出指定版本发布说明。"""
    changelog_text = options.changelog_path.read_text(encoding="utf-8")
    notes = extract_release_notes_section(
        changelog_text=changelog_text,
        tag=options.tag,
    )
    options.output_path.parent.mkdir(parents=True, exist_ok=True)
    options.output_path.write_text(notes, encoding="utf-8")


def main() -> int:
    """执行 Release 正文提取。"""
    write_release_notes(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
