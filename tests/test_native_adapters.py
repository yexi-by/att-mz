"""Rust 原生适配层协议薄契约测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

from app import native_quality, native_scope_index, native_write_plan
from app.config.schemas import TextRulesSetting
from app.language_profiles import build_text_rules_setting_for_language_profile
from app.persistence.sql import CURRENT_TEXT_FACT_CONTRACT_VERSION
from app.rmmz.json_types import JsonObject
from app.rmmz.schema import TranslationItem
from app.rmmz.text_rules import JsonArray, TextRules


class _FakeWritePlanModule:
    """返回固定写回计划 JSON 的测试模块。"""

    def __init__(self, payload: dict[str, object]) -> None:
        """保存待返回的 JSON 对象。"""
        self._payload = payload

    def build_write_back_plan(
        self,
        game_path: str,
        db_path: str,
        setting_payload_json: str,
        mode: str,
        confirm_font_overwrite: bool,
    ) -> str:
        """返回测试预置的写回计划。"""
        _ = (game_path, db_path, setting_payload_json, mode, confirm_font_overwrite)
        return json.dumps(self._payload, ensure_ascii=False)


class _FakeScopeIndexModule:
    """返回固定 Scope/Index JSON 的测试模块。"""

    def __init__(
        self,
        payload: dict[str, object] | None = None,
        *,
        schema_fingerprint: str = "invalid-schema-fingerprint",
    ) -> None:
        """保存待返回的 JSON 对象。"""
        self._payload = payload or {}
        self._schema_fingerprint = schema_fingerprint

    def scan_rule_candidates(self, payload_json: str) -> str:
        """返回测试预置的规则候选扫描结果。"""
        _ = payload_json
        payload = {
            "schema_version": 1,
            "contract_versions": {
                "rust_scope_facts": native_scope_index.RUST_SCOPE_FACTS_CONTRACT_VERSION,
                "parser": native_scope_index.PARSER_CONTRACT_VERSION,
                "source_branch": native_scope_index.SOURCE_BRANCH_CONTRACT_VERSION,
                "text_fact_schema": CURRENT_TEXT_FACT_CONTRACT_VERSION,
            },
            **self._payload,
        }
        return json.dumps(payload, ensure_ascii=False)

    def native_schema_fingerprint(self) -> str:
        """返回测试预置的 schema 指纹。"""
        return self._schema_fingerprint


class _FakeQualityModule:
    """返回固定 native quality JSON 的测试模块。"""

    def __init__(
        self,
        quality_counts: dict[str, object],
        protocol_counts: dict[str, object],
    ) -> None:
        """保存待返回的计数对象。"""
        self._quality_counts = quality_counts
        self._protocol_counts = protocol_counts
        self.configured_values: list[int | None] = []

    def scan_quality_counts(self, payload_json: str) -> str:
        """返回测试预置的质检计数。"""
        _ = payload_json
        return json.dumps(self._quality_counts, ensure_ascii=False)

    def scan_write_protocol_count(self, payload_json: str) -> str:
        """返回测试预置的写入协议计数。"""
        _ = payload_json
        return json.dumps(self._protocol_counts, ensure_ascii=False)

    def configure_runtime_threads(self, rust_threads: int | None) -> None:
        """记录线程配置。"""
        self.configured_values.append(rust_threads)

    def native_thread_count(self) -> int:
        """返回当前记录的线程数。"""
        configured_value = self.configured_values[-1] if self.configured_values else None
        return configured_value if configured_value is not None else 7


def _minimal_write_plan_payload() -> dict[str, object]:
    """构造满足适配层解析的最小写回计划。"""
    return {
        "status": "ok",
        "files": [],
        "plugin_source_runtime_write_maps": [],
        "font_replacement_records": [],
        "summary": {
            "data_item_count": 0,
            "plugin_item_count": 0,
            "terminology_written_count": 0,
            "target_font_name": None,
            "source_font_count": 0,
            "replaced_font_reference_count": 0,
            "font_copied": False,
            "planned_file_count": 0,
            "skipped_file_count": 0,
            "plugin_source_ast_source_scan_file_count": 0,
            "plugin_source_ast_runtime_scan_file_count": 0,
            "plugin_source_runtime_map_count": 0,
        },
        "timings_ms": {"total": 1},
    }


def _sample_translation_item() -> TranslationItem:
    """构造原生适配层测试用译文条目。"""
    return TranslationItem(
        location_path="Items.json/1/name",
        item_type="short_text",
        original_lines=["薬草"],
        source_line_paths=["Items.json/1/name"],
        translation_lines=["草药"],
    )


def test_native_write_plan_rejects_target_path_outside_content_root(
    monkeypatch: MonkeyPatch,
) -> None:
    """Python 适配层必须拦截 Rust 返回的越界目标路径。"""
    payload = _minimal_write_plan_payload()
    payload["files"] = [
        {
            "target_path": str(Path("outside") / "System.json"),
            "relative_path": "data/System.json",
            "content": "{}\n",
        }
    ]

    monkeypatch.setattr(
        native_write_plan,
        "_load_native_module",
        lambda: cast(native_write_plan.NativeWritePlanModule, _FakeWritePlanModule(payload)),
    )

    with pytest.raises(RuntimeError, match="目标路径不在游戏内容目录内"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("game"),
            content_root=Path("game"),
            db_path=Path("game.db"),
            mode="rebuild_active_runtime",
            confirm_font_overwrite=False,
        )


def test_native_rule_candidates_requires_scan_summary(monkeypatch: MonkeyPatch) -> None:
    """规则候选结果必须包含 scan_summary。"""
    fake_module = _FakeScopeIndexModule({"candidates": [], "candidate_summary": []})
    monkeypatch.setattr(
        native_scope_index,
        "_load_native_scope_index_module",
        lambda: cast(native_scope_index.NativeScopeIndexModule, fake_module),
    )

    with pytest.raises(KeyError):
        _ = native_scope_index.scan_native_rule_candidates(cast(JsonObject, {}))


def test_native_schema_fingerprint_rejects_mismatched_schema(monkeypatch: MonkeyPatch) -> None:
    """Python adapter 不能接受不满足当前要求的 schema 指纹。"""
    fake_module = _FakeScopeIndexModule(schema_fingerprint="invalid-schema-fingerprint")
    monkeypatch.setattr(
        native_scope_index,
        "_load_native_scope_index_module",
        lambda: cast(native_scope_index.NativeScopeIndexModule, fake_module),
    )

    with pytest.raises(RuntimeError, match="rebuild-text-index"):
        _ = native_scope_index.native_schema_fingerprint()


def test_native_runtime_thread_config_maps_auto_and_positive_values(
    monkeypatch: MonkeyPatch,
) -> None:
    """Python adapter 必须把 auto 转成 None，正整数原样传给 Rust。"""
    fake_module = _FakeQualityModule(
        {
            "source_residual_count": 0,
            "text_structure_count": 0,
            "placeholder_risk_count": 0,
            "overwide_line_count": 0,
        },
        {"write_protocol_count": 0},
    )
    monkeypatch.setattr(
        native_quality,
        "_load_native_module",
        lambda: cast(native_quality.NativeModule, fake_module),
    )

    native_quality.configure_native_runtime_threads("auto")
    native_quality.configure_native_runtime_threads(4)

    assert fake_module.configured_values == [None, 4]
    assert native_quality.native_thread_count() == 4


def test_native_text_rules_payload_includes_source_copy_residual_policy() -> None:
    """英文源文复制残留配置必须进入 Rust 质检载荷。"""
    text_rules = TextRules.from_setting(build_text_rules_setting_for_language_profile("en"))

    payload = native_quality.build_native_text_rules_payload(text_rules)

    assert payload["source_residual_detection_profile"] == "english_source_copy"
    assert payload["english_source_copy_min_words"] == 4
    assert payload["english_source_copy_min_letters"] == 12
    assert payload["allowed_source_residual_terms"] == []


def test_native_quality_counts_reject_bad_count_types(monkeypatch: MonkeyPatch) -> None:
    """Rust 计数结果类型错误时必须直接报错。"""
    fake_module = _FakeQualityModule(
        {
            "source_residual_count": True,
            "text_structure_count": 0,
            "placeholder_risk_count": 0,
            "overwide_line_count": 0,
        },
        {"write_protocol_count": -1},
    )
    monkeypatch.setattr(
        native_quality,
        "_load_native_module",
        lambda: cast(native_quality.NativeModule, fake_module),
    )

    with pytest.raises(TypeError, match="source_residual_count 必须是非负整数"):
        _ = native_quality.collect_native_quality_counts(
            items=[_sample_translation_item()],
            text_rules=TextRules.from_setting(TextRulesSetting()),
            source_residual_rules=[],
        )
    with pytest.raises(TypeError, match="write_protocol_count 必须是非负整数"):
        _ = native_quality.count_native_write_protocol_issues(
            game_data=cast(JsonObject, {}),
            plugins_js=cast(JsonArray, []),
            items=[],
        )
