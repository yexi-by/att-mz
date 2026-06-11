"""Agent 规则导入与 Rust rule_runtime commit 的薄编排。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.application.rule_import_backup import RuleImportBackupDomain, write_rule_import_translation_backup
from app.native_rule_runtime import RuleImportCommitResult, RuleImportPrepareResult, commit_rule_import
from app.rmmz.json_types import JsonArray, JsonObject, ensure_json_array, ensure_json_object
from app.rmmz.schema import TranslationItem
from app.text_fact_identity import require_translation_fact_identities

if TYPE_CHECKING:
    from app.agent_toolkit.services.rule_identity import RuleFactHit
    from app.persistence import TargetGameSession


def empty_cleanup_input() -> JsonObject:
    """构造没有待比对译文的 cleanup 输入。"""
    old_identities: JsonArray = []
    current_identities: JsonArray = []
    return {
        "old_translation_identities": old_identities,
        "current_rule_identities": current_identities,
    }


def cleanup_input_from_stale_items(items: list[TranslationItem]) -> JsonObject:
    """把已判定需要复核的译文收窄为 Rust prepare 可计算的 cleanup 输入。"""
    identities: JsonArray = []
    for fact_id, raw_hash, translatable_hash in require_translation_fact_identities(items):
        identities.append(
            {
                "fact_id": fact_id,
                "source_fact_raw_hash": raw_hash,
                "source_fact_translatable_hash": translatable_hash,
            }
        )
    current_identities: JsonArray = []
    return {
        "old_translation_identities": identities,
        "current_rule_identities": current_identities,
    }


def cleanup_input_from_rule_hits(
    *,
    old_items: list[TranslationItem],
    current_rule_hits: list[RuleFactHit],
) -> JsonObject:
    """把旧译文和当前规则命中交给 Rust prepare 计算失效译文差集。"""
    old_identities: JsonArray = []
    for fact_id, raw_hash, translatable_hash in require_translation_fact_identities(old_items):
        old_identities.append(
            {
                "fact_id": fact_id,
                "source_fact_raw_hash": raw_hash,
                "source_fact_translatable_hash": translatable_hash,
            }
        )
    current_identities: JsonArray = []
    for hit in current_rule_hits:
        current_identities.append(
            {
                "fact_id": hit.fact_id,
                "source_fact_raw_hash": hit.source_fact_raw_hash,
                "source_fact_translatable_hash": hit.source_fact_translatable_hash,
            }
        )
    return {
        "old_translation_identities": old_identities,
        "current_rule_identities": current_identities,
    }


async def write_prepared_cleanup_backup(
    *,
    session: TargetGameSession,
    game_title: str,
    backup_domain: RuleImportBackupDomain,
    prepare_result: RuleImportPrepareResult,
    output_dir: Path | None = None,
) -> tuple[int, str | None, JsonObject]:
    """按 Rust prepare 给出的 fact_id 写备份文件，不删除数据库译文。"""
    fact_ids = prepared_cleanup_fact_ids(prepare_result)
    if not fact_ids:
        return 0, None, _cleanup_details(domain=backup_domain, backup_path=None, items=[])
    stale_items = await session.read_translated_items_by_fact_ids(fact_ids)
    backup = await write_rule_import_translation_backup(
        game_title=game_title,
        domain=backup_domain,
        items=stale_items,
        output_dir=output_dir,
    )
    backup_path = backup.backup_path if backup is not None else None
    return (
        len(stale_items),
        backup_path,
        _cleanup_details(domain=backup_domain, backup_path=backup_path, items=stale_items),
    )


def commit_prepared_rule_import(
    *,
    db_path: Path,
    domain: str,
    prepare_result: RuleImportPrepareResult,
    backup_path: str | None,
) -> RuleImportCommitResult:
    """提交 Rust prepare 生成的 opaque plan。"""
    if prepare_result.plan_token is None or prepare_result.prepared_plan is None:
        raise RuntimeError(f"{domain} 规则导入缺少 rule_runtime prepared plan")
    return commit_rule_import(
        {
            "db_path": str(db_path),
            "domain": domain,
            "plan_token": prepare_result.plan_token,
            "prepared_plan": prepare_result.prepared_plan,
            "backup_path": backup_path,
        }
    )


def commit_deleted_translation_count(commit_result: RuleImportCommitResult) -> int:
    """读取 Rust commit 报告中的实际清理数量。"""
    cleanup_plan = ensure_json_object(
        commit_result.summary.get("cleanup_plan", {}),
        "rule_runtime.commit.summary.cleanup_plan",
    )
    value = cleanup_plan.get("deleted_translation_count", 0)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("rule_runtime.commit.summary.cleanup_plan.deleted_translation_count 必须是整数")
    return value


def prepared_cleanup_fact_ids(prepare_result: RuleImportPrepareResult) -> list[str]:
    """读取 Rust prepare 报告中的待清理 fact_id。"""
    cleanup_plan = ensure_json_object(
        prepare_result.details.get("cleanup_plan", {}),
        "rule_runtime.prepare.details.cleanup_plan",
    )
    records = ensure_json_array(
        cleanup_plan.get("records", []),
        "rule_runtime.prepare.details.cleanup_plan.records",
    )
    fact_ids: list[str] = []
    for index, raw_record in enumerate(records):
        record = ensure_json_object(
            raw_record,
            f"rule_runtime.prepare.details.cleanup_plan.records[{index}]",
        )
        fact_id = record.get("fact_id")
        if not isinstance(fact_id, str):
            raise TypeError(
                f"rule_runtime.prepare.details.cleanup_plan.records[{index}].fact_id 必须是字符串"
            )
        fact_ids.append(fact_id)
    return fact_ids


def _cleanup_details(
    *,
    domain: str,
    backup_path: str | None,
    items: list[TranslationItem],
) -> JsonObject:
    item_payload: JsonArray = []
    for item in items:
        item_payload.append(
            {
                "fact_id": item.fact_id,
                "location_path": item.location_path,
                "item_type": item.item_type,
            }
        )
    return {
        "domain": domain,
        "deleted_translation_count": len(items),
        "backup_required": bool(items),
        "backup_path": backup_path,
        "items": item_payload,
    }
