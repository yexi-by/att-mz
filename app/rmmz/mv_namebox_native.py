"""MV 虚拟名字框 native 候选和规则命中适配。"""

from __future__ import annotations

from dataclasses import dataclass

from app.native_scope_index import (
    NativeRuleCandidatesResult,
    build_native_mv_virtual_namebox_candidates_payload,
    mv_virtual_namebox_rule_records_to_native_rules,
    scan_native_rule_candidates,
)
from app.rmmz.json_types import JsonArray, JsonObject, ensure_json_array, ensure_json_object
from app.rmmz.schema import GameData, MvVirtualNameboxRuleRecord


@dataclass(frozen=True, slots=True)
class NativeMvVirtualNameboxScan:
    """MV 虚拟名字框 native 扫描结果。"""

    candidate_details: JsonArray
    rule_errors: JsonArray
    match_details: JsonArray
    speaker_requirements: list["NativeMvVirtualNameboxSpeakerRequirement"]
    scope_hash: str

    @property
    def candidate_count(self) -> int:
        """候选数量。"""
        return len(self.candidate_details)

    @property
    def matched_candidate_count(self) -> int:
        """命中候选数量。"""
        return len(self.match_details)


@dataclass(frozen=True, slots=True)
class NativeMvVirtualNameboxSpeakerRequirement:
    """native 产出的 MV 说话人译名需求。"""

    source_text: str
    policy: str
    requires_speaker_name: bool
    rule_name: str
    location_paths: list[str]
    sample_body_lines: list[str]
    render_template: str
    confidence: str


def scan_native_mv_virtual_namebox(
    *,
    game_data: GameData,
    records: list[MvVirtualNameboxRuleRecord] | None = None,
) -> NativeMvVirtualNameboxScan:
    """调用 Rust 生成 MV 虚拟名字框候选和可选规则命中。"""
    native_result = scan_native_rule_candidates(
        build_native_mv_virtual_namebox_candidates_payload(
            game_data=game_data,
            rules=mv_virtual_namebox_rule_records_to_native_rules(records or []),
        )
    )
    return _scan_from_native_result(native_result)


def native_mv_virtual_namebox_candidates_payload(game_data: GameData) -> JsonObject:
    """生成 MV 虚拟名字框候选导出 JSON。"""
    scan = scan_native_mv_virtual_namebox(game_data=game_data)
    return {
        "engine_kind": game_data.layout.engine_kind,
        "scope_hash": scan.scope_hash,
        "candidate_count": scan.candidate_count,
        "candidates": scan.candidate_details,
        "speaker_requirements": [
            {
                "source_text": requirement.source_text,
                "policy": requirement.policy,
                "requires_speaker_name": requirement.requires_speaker_name,
                "rule_name": requirement.rule_name,
                "location_paths": list(requirement.location_paths),
                "sample_body_lines": list(requirement.sample_body_lines),
                "render_template": requirement.render_template,
                "confidence": requirement.confidence,
            }
            for requirement in scan.speaker_requirements
        ],
    }


def _scan_from_native_result(native_result: NativeRuleCandidatesResult) -> NativeMvVirtualNameboxScan:
    summary = ensure_json_object(
        native_result.scan_summary["mv_virtual_namebox"],
        "native_rule_candidates_result.scan_summary.mv_virtual_namebox",
    )
    return NativeMvVirtualNameboxScan(
        candidate_details=ensure_json_array(
            summary["candidate_details"],
            "native_rule_candidates_result.scan_summary.mv_virtual_namebox.candidate_details",
        ),
        rule_errors=ensure_json_array(
            summary["errors"],
            "native_rule_candidates_result.scan_summary.mv_virtual_namebox.errors",
        ),
        match_details=ensure_json_array(
            summary["hit_details"],
            "native_rule_candidates_result.scan_summary.mv_virtual_namebox.hit_details",
        ),
        speaker_requirements=_read_speaker_requirements(summary),
        scope_hash=_read_string(
            summary,
            "scope_hash",
            "native_rule_candidates_result.scan_summary.mv_virtual_namebox",
        ),
    )


def _read_string(payload: JsonObject, field_name: str, context: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str):
        raise TypeError(f"{context}.{field_name} 必须是字符串")
    return value


def _read_string_array(payload: JsonObject, field_name: str, context: str) -> list[str]:
    values: list[str] = []
    for index, value in enumerate(ensure_json_array(payload[field_name], f"{context}.{field_name}")):
        if not isinstance(value, str):
            raise TypeError(f"{context}.{field_name}[{index}] 必须是字符串")
        values.append(value)
    return values


def _read_speaker_requirements(summary: JsonObject) -> list[NativeMvVirtualNameboxSpeakerRequirement]:
    requirements: list[NativeMvVirtualNameboxSpeakerRequirement] = []
    for index, raw_requirement in enumerate(
        ensure_json_array(
            summary["speaker_requirements"],
            "native_rule_candidates_result.scan_summary.mv_virtual_namebox.speaker_requirements",
        )
    ):
        context = f"native_rule_candidates_result.scan_summary.mv_virtual_namebox.speaker_requirements[{index}]"
        requirement = ensure_json_object(raw_requirement, context)
        requirements.append(
            NativeMvVirtualNameboxSpeakerRequirement(
                source_text=_read_string(requirement, "source_text", context),
                policy=_read_string(requirement, "policy", context),
                requires_speaker_name=_read_bool(requirement, "requires_speaker_name", context),
                rule_name=_read_string(requirement, "rule_name", context),
                location_paths=_read_string_array(requirement, "location_paths", context),
                sample_body_lines=_read_string_array(requirement, "sample_body_lines", context),
                render_template=_read_string(requirement, "render_template", context),
                confidence=_read_string(requirement, "confidence", context),
            )
        )
    return requirements


def _read_bool(payload: JsonObject, field_name: str, context: str) -> bool:
    value = payload[field_name]
    if not isinstance(value, bool):
        raise TypeError(f"{context}.{field_name} 必须是布尔值")
    return value


__all__ = [
    "NativeMvVirtualNameboxScan",
    "NativeMvVirtualNameboxSpeakerRequirement",
    "native_mv_virtual_namebox_candidates_payload",
    "scan_native_mv_virtual_namebox",
]
