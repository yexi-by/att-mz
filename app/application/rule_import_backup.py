"""规则导入清理已保存译文前的备份工具。"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import aiofiles

from app.rmmz.schema import TranslationItem
from app.rmmz.text_rules import JsonObject
from app.runtime_paths import resolve_app_path

type RuleImportBackupDomain = Literal[
    "plugin-rules",
    "event-command-rules",
    "note-tag-rules",
    "plugin-source-rules",
    "placeholder-rules",
    "structured-placeholder-rules",
]


@dataclass(frozen=True, slots=True)
class RuleImportBackupSummary:
    """规则导入清理译文前生成的备份摘要。"""

    backup_path: str
    item_count: int


async def write_rule_import_translation_backup(
    *,
    game_title: str,
    domain: RuleImportBackupDomain,
    items: list[TranslationItem],
    output_dir: Path | None = None,
) -> RuleImportBackupSummary | None:
    """把即将清理的已保存译文写成可重新导入的备份 JSON。"""
    if not items:
        return None

    backup_path = _build_backup_path(
        game_title=game_title,
        domain=domain,
        output_dir=output_dir,
    )
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_backup_payload(items)
    async with aiofiles.open(backup_path, "w", encoding="utf-8") as file:
        _ = await file.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")
    return RuleImportBackupSummary(
        backup_path=str(backup_path),
        item_count=len(items),
    )


def _build_backup_path(
    *,
    game_title: str,
    domain: RuleImportBackupDomain,
    output_dir: Path | None,
) -> Path:
    """生成稳定可定位的规则导入译文备份路径。"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_game_title = _safe_filename_part(game_title)
    if output_dir is not None:
        return (
            output_dir
            / "rule-import-backups"
            / safe_game_title
            / f"{domain}-{timestamp}.json"
        )
    return resolve_app_path(
        "outputs",
        "rule-import-backups",
        safe_game_title,
        f"{domain}-{timestamp}.json",
    )


def _safe_filename_part(value: str) -> str:
    """把游戏标题收窄为可安全用作文件名的片段。"""
    stripped_value = value.strip()
    if not stripped_value:
        return "game"
    normalized_value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stripped_value)
    normalized_value = normalized_value.strip(" ._")
    return normalized_value or "game"


def _build_backup_payload(items: list[TranslationItem]) -> JsonObject:
    """生成可作为 `import-manual-translations` 输入的备份内容。"""
    payload: JsonObject = {}
    for item in items:
        payload[item.location_path] = {
            "item_type": item.item_type,
            "role": item.role,
            "original_lines": [line for line in item.original_lines],
            "source_line_paths": [path for path in item.source_line_paths],
            "translation_lines": [line for line in item.translation_lines],
            "restore_note": "重新导入正确规则后，可用本文件恢复这些已保存译文。",
        }
    return payload


__all__: list[str] = [
    "RuleImportBackupDomain",
    "RuleImportBackupSummary",
    "write_rule_import_translation_backup",
]
