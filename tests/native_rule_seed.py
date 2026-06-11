"""测试专用的 rule_runtime native seed helper。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.config.schemas import TextRulesSetting
from app.native_rule_runtime import (
    commit_rule_import,
    prepare_rule_import,
    runtime_config_patterns_from_setting,
)
from app.rmmz.json_types import JsonArray, JsonObject, JsonValue
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    MvVirtualNameboxRuleRecord,
    NonstandardDataTextRuleRecord,
    NoteTagTextRuleRecord,
    PlaceholderRuleRecord,
    PluginSourceTextRuleRecord,
    PluginTextRuleRecord,
    SourceResidualRuleRecord,
    StructuredPlaceholderRuleRecord,
)
from app.rule_review import RuleReviewDomain, rule_runtime_domain_for_review_domain

if TYPE_CHECKING:
    from app.persistence import TargetGameSession


async def seed_native_rule_import(
    session: TargetGameSession,
    *,
    domain: str,
    rules_payload: JsonValue,
    confirm_empty: bool = False,
    scope_hash: str | None = None,
) -> None:
    """通过 Rust prepare/commit 写入当前测试数据库。"""
    await session.commit()
    prepare_result = prepare_rule_import(
        {
            "mode": "test_seed",
            "db_path": str(session.db_path),
            "domain": domain,
            "rules_payload": rules_payload,
            "game_context": _seed_game_context(scope_hash),
            "settings_runtime_patterns": runtime_config_patterns_from_setting(TextRulesSetting()),
            "confirm_empty": confirm_empty,
        }
    )
    if prepare_result.status != "ok":
        messages = "; ".join(issue.message for issue in prepare_result.errors)
        raise AssertionError(f"native rule seed prepare failed for {domain}: {messages}")
    if prepare_result.plan_token is None or prepare_result.prepared_plan is None:
        raise AssertionError(f"native rule seed missing prepared plan for {domain}")
    commit_result = commit_rule_import(
        {
            "db_path": str(session.db_path),
            "domain": domain,
            "plan_token": prepare_result.plan_token,
            "prepared_plan": prepare_result.prepared_plan,
            "backup_path": None,
        }
    )
    if commit_result.status != "ok":
        messages = "; ".join(issue.message for issue in commit_result.errors)
        raise AssertionError(f"native rule seed commit failed for {domain}: {messages}")


async def seed_native_plugin_text_rules(
    session: TargetGameSession,
    rule_records: Sequence[PluginTextRuleRecord],
) -> None:
    await seed_native_rule_import(
        session,
        domain="plugin_config",
        rules_payload=[record.model_dump(mode="json") for record in rule_records],
    )


async def seed_native_plugin_source_text_rules(
    session: TargetGameSession,
    rule_records: Sequence[PluginSourceTextRuleRecord],
) -> None:
    await seed_native_rule_import(
        session,
        domain="plugin_source",
        rules_payload={"rules": [record.model_dump(mode="json") for record in rule_records]},
    )


async def seed_native_nonstandard_data_text_rules(
    session: TargetGameSession,
    rule_records: Sequence[NonstandardDataTextRuleRecord],
) -> None:
    await seed_native_rule_import(
        session,
        domain="nonstandard_data",
        rules_payload=[record.model_dump(mode="json") for record in rule_records],
    )


async def seed_native_event_command_text_rules(
    session: TargetGameSession,
    rule_records: Sequence[EventCommandTextRuleRecord],
) -> None:
    await seed_native_rule_import(
        session,
        domain="event_commands",
        rules_payload=[record.model_dump(mode="json") for record in rule_records],
    )


async def seed_native_note_tag_text_rules(
    session: TargetGameSession,
    rule_records: Sequence[NoteTagTextRuleRecord],
) -> None:
    rules_payload: JsonObject = {
        record.file_name: list(record.tag_names) for record in rule_records
    }
    await seed_native_rule_import(
        session,
        domain="note_tags",
        rules_payload=rules_payload,
    )


async def seed_native_placeholder_rules(
    session: TargetGameSession,
    rule_records: Sequence[PlaceholderRuleRecord],
) -> None:
    rules_payload: JsonObject = {
        record.pattern_text: record.placeholder_template for record in rule_records
    }
    await seed_native_rule_import(
        session,
        domain="placeholders",
        rules_payload=rules_payload,
    )


async def seed_native_structured_placeholder_rules(
    session: TargetGameSession,
    rule_records: Sequence[StructuredPlaceholderRuleRecord],
) -> None:
    await seed_native_rule_import(
        session,
        domain="structured_placeholders",
        rules_payload={
            "paired_shell_rules": [
                {
                    "name": record.rule_name,
                    "rule_type": record.rule_type,
                    "pattern": record.pattern_text,
                    "translatable_group": record.translatable_group,
                    "protected_groups": dict(record.protected_groups),
                }
                for record in rule_records
            ]
        },
    )


async def seed_native_source_residual_rules(
    session: TargetGameSession,
    rule_records: Sequence[SourceResidualRuleRecord],
) -> None:
    position_rules: JsonObject = {}
    structural_rules: JsonArray = []
    for record in rule_records:
        if record.rule_type == "position":
            position_rules[record.location_path] = {
                "rule_id": record.rule_id,
                "allowed_terms": list(record.allowed_terms),
                "reason": record.reason,
            }
            continue
        structural_rules.append(
            {
                "rule_id": record.rule_id,
                "pattern": record.pattern_text,
                "check_group": record.check_group,
                "allowed_terms": list(record.allowed_terms),
                "reason": record.reason,
            }
        )
    await seed_native_rule_import(
        session,
        domain="source_residual",
        rules_payload={
            "position_rules": position_rules,
            "structural_rules": structural_rules,
        },
    )


async def seed_native_mv_virtual_namebox_rules(
    session: TargetGameSession,
    rule_records: Sequence[MvVirtualNameboxRuleRecord],
) -> None:
    await seed_native_rule_import(
        session,
        domain="mv_virtual_namebox",
        rules_payload={
            "rules": [
                {
                    "name": record.rule_name,
                    "pattern": record.pattern_text,
                    "speaker_group": record.speaker_group,
                    "body_group": record.body_group,
                    "speaker_policy": record.speaker_policy,
                    "render_template": record.render_template,
                }
                for record in rule_records
            ]
        },
    )


async def seed_native_empty_rule_review_state(
    session: TargetGameSession,
    *,
    rule_domain: RuleReviewDomain,
    scope_hash: str,
) -> None:
    await seed_native_rule_import(
        session,
        domain=rule_runtime_domain_for_review_domain(rule_domain),
        rules_payload=_empty_rules_payload_for_domain(rule_runtime_domain_for_review_domain(rule_domain)),
        confirm_empty=True,
        scope_hash=scope_hash,
    )


def _seed_game_context(scope_hash: str | None) -> JsonObject:
    if scope_hash is None:
        return {"scope_hash": "test-seed"}
    return {"scope_hash": scope_hash}


def _empty_rules_payload_for_domain(domain: str) -> JsonValue:
    if domain in {"plugin_config", "event_commands", "nonstandard_data"}:
        return []
    if domain == "plugin_source":
        return {"rules": []}
    if domain in {"placeholders", "note_tags"}:
        return {}
    if domain == "structured_placeholders":
        return {"paired_shell_rules": []}
    if domain == "source_residual":
        return {"position_rules": {}, "structural_rules": []}
    if domain == "mv_virtual_namebox":
        return {"rules": []}
    raise AssertionError(f"unknown native rule seed domain: {domain}")


async def insert_corrupt_native_rule_row(
    session: TargetGameSession,
    *,
    domain: str,
    matcher_kind: str,
    matcher_value: str,
    payload_json: JsonObject,
    rule_order: int = 0,
) -> None:
    """为损坏数据库测试插入无法通过 native prepare 的统一规则行。"""
    _ = await session.connection.execute(
        """
        INSERT INTO rules(
            rule_id,
            domain,
            rule_order,
            matcher_kind,
            matcher_value,
            payload_json,
            enabled,
            source_kind,
            rule_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, 'corrupt_test', ?)
        """,
        (
            f"corrupt:{domain}:{rule_order}",
            domain,
            rule_order,
            matcher_kind,
            matcher_value,
            json.dumps(payload_json, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            f"corrupt-hash:{domain}:{rule_order}",
        ),
    )
    await session.commit()
