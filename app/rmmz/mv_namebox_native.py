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
from app.rmmz.mv_namebox import MvVirtualNameboxCandidate
from app.rmmz.schema import GameData, MvVirtualNameboxRuleRecord


@dataclass(frozen=True, slots=True)
class NativeMvVirtualNameboxScan:
    """MV 虚拟名字框 native 扫描结果。"""

    candidate_details: JsonArray
    rule_errors: JsonArray
    match_details: JsonArray

    @property
    def candidate_count(self) -> int:
        """候选数量。"""
        return len(self.candidate_details)

    @property
    def matched_candidate_count(self) -> int:
        """命中候选数量。"""
        return len(self.match_details)


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
        "candidate_count": scan.candidate_count,
        "candidates": scan.candidate_details,
    }


def native_mv_virtual_namebox_candidates_from_details(candidate_details: JsonArray) -> list[MvVirtualNameboxCandidate]:
    """把 native 候选明细转换为旧规则匹配 helper 可消费的候选对象。"""
    candidates: list[MvVirtualNameboxCandidate] = []
    for index, raw_detail in enumerate(candidate_details):
        detail = ensure_json_object(raw_detail, f"mv_virtual_namebox.candidate_details[{index}]")
        candidates.append(
            MvVirtualNameboxCandidate(
                location_path=_read_string(detail, "location_path", f"mv_virtual_namebox.candidate_details[{index}]"),
                text=_read_string(detail, "text", f"mv_virtual_namebox.candidate_details[{index}]"),
                following_lines=_read_string_array(
                    detail,
                    "following_lines",
                    f"mv_virtual_namebox.candidate_details[{index}]",
                ),
            )
        )
    return candidates


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


__all__ = [
    "NativeMvVirtualNameboxScan",
    "native_mv_virtual_namebox_candidates_from_details",
    "native_mv_virtual_namebox_candidates_payload",
    "scan_native_mv_virtual_namebox",
]
