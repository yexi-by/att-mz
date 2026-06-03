"""阶段 0 发行包布局护栏。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from scripts import build_release


def test_copy_release_resources_packages_release_skill_and_required_layout(tmp_path: Path) -> None:
    """发行资源复制只带发行版所需文件，不把开发态 Skill 和源码目录带入包内。"""
    release_dir = tmp_path / build_release.RELEASE_DIRECTORY_NAME

    build_release.copy_release_resources(release_dir)

    packaged_skill = release_dir / "skills" / "att-mz" / "SKILL.md"
    packaged_references = release_dir / "skills" / "att-mz" / "references"
    source_references = build_release.RELEASE_SKILL_REFERENCES_SOURCE
    assert (release_dir / "README.md").is_file()
    assert (release_dir / "LICENSE").is_file()
    assert (release_dir / "setting.toml").is_file()
    assert (release_dir / "setting.example.toml").is_file()
    assert (release_dir / "custom_placeholder_rules.json").is_file()
    assert (release_dir / "prompts" / "text_translation_ja_to_zh_system.md").is_file()
    assert (release_dir / "prompts" / "text_translation_en_to_zh_system.md").is_file()
    assert (release_dir / "fonts" / "NotoSansSC-Regular.ttf").is_file()
    assert packaged_skill.is_file()
    assert packaged_references.is_dir()
    assert (release_dir / "data" / "db").is_dir()
    assert (release_dir / "logs").is_dir()
    assert (release_dir / "outputs").is_dir()
    skill_text = packaged_skill.read_text(encoding="utf-8")
    assert skill_text.startswith("---\nname: att-mz\n")
    assert "name: att-mz-release" not in skill_text
    assert {path.name for path in packaged_references.glob("*.md")} == {
        path.name for path in source_references.glob("*.md")
    }
    assert not any((release_dir / "data" / "db").iterdir())
    assert not any((release_dir / "logs").iterdir())
    assert not any((release_dir / "outputs").iterdir())
    for forbidden_relative in ("app", "tests", "rust", ".github", ".git", "skills/att-mz-release"):
        assert not (release_dir / forbidden_relative).exists()


def test_create_release_zip_preserves_empty_runtime_directories(tmp_path: Path) -> None:
    """发行 ZIP 必须保留空数据、日志和输出目录。"""
    release_dir = tmp_path / build_release.RELEASE_DIRECTORY_NAME
    zip_path = tmp_path / build_release.DEFAULT_ZIP_NAME

    build_release.copy_release_resources(release_dir)
    build_release.create_release_zip(release_dir, zip_path)

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    root = build_release.RELEASE_DIRECTORY_NAME
    assert f"{root}/data/db/" in names
    assert f"{root}/logs/" in names
    assert f"{root}/outputs/" in names
    assert f"{root}/skills/att-mz/SKILL.md" in names
    assert f"{root}/skills/att-mz-release/" not in names
