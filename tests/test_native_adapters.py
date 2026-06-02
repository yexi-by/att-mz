"""Rust 原生适配层协议校验测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from app import native_javascript_ast, native_quality, native_write_plan
from app.config.schemas import TextRulesSetting
from app.language_profiles import build_text_rules_setting_for_language_profile
from app.rmmz.schema import TranslationItem
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules


class _FakeWritePlanModule:
    """返回固定写回计划 JSON 的测试模块。"""

    _payload: dict[str, object]
    setting_payloads: list[dict[str, object]]

    def __init__(self, payload: dict[str, object]) -> None:
        """保存待返回的 JSON 对象。"""
        self._payload = payload
        self.setting_payloads = []

    def native_contract_version(self) -> int:
        """返回当前测试契约版本。"""
        return native_write_plan.NATIVE_CONTRACT_VERSION

    def build_write_back_plan(
        self,
        game_path: str,
        db_path: str,
        setting_payload_json: str,
        mode: str,
        confirm_font_overwrite: bool,
    ) -> str:
        """返回测试预置的写回计划。"""
        _ = (game_path, db_path, mode, confirm_font_overwrite)
        raw_payload = cast(object, json.loads(setting_payload_json))
        assert isinstance(raw_payload, dict)
        self.setting_payloads.append(cast(dict[str, object], raw_payload))
        return json.dumps(self._payload, ensure_ascii=False)


class _FakeJavaScriptAstModule:
    """返回固定 JavaScript AST JSON 的测试模块。"""

    _payload: dict[str, object]

    def __init__(self, payload: dict[str, object]) -> None:
        """保存待返回的 JSON 对象。"""
        self._payload = payload

    def parse_javascript_string_spans(self, payload_json: str) -> str:
        """返回测试预置的 AST 扫描结果。"""
        _ = payload_json
        return json.dumps(self._payload, ensure_ascii=False)

    def parse_javascript_string_spans_batch(self, payload_json: str) -> str:
        """返回测试预置的批量 AST 扫描结果。"""
        _ = payload_json
        return json.dumps({"files": [{"file_name": "test.js", **self._payload}]}, ensure_ascii=False)


class _FakeQualityModule:
    """返回固定原生质检计数 JSON 的测试模块。"""

    _quality_payload: dict[str, object]
    _protocol_payload: dict[str, object]

    def __init__(self, quality_payload: dict[str, object], protocol_payload: dict[str, object]) -> None:
        """保存待返回的计数 JSON 对象。"""
        self._quality_payload = quality_payload
        self._protocol_payload = protocol_payload

    def native_contract_version(self) -> int:
        """返回当前测试契约版本。"""
        return native_quality.NATIVE_CONTRACT_VERSION

    def scan_quality_counts(self, payload_json: str) -> str:
        """返回测试预置的质检计数。"""
        _ = payload_json
        return json.dumps(self._quality_payload, ensure_ascii=False)

    def scan_write_protocol_count(self, payload_json: str) -> str:
        """返回测试预置的写入协议计数。"""
        _ = payload_json
        return json.dumps(self._protocol_payload, ensure_ascii=False)

    def scan_quality(self, payload_json: str) -> str:
        """计数路径不应请求完整质检明细。"""
        _ = payload_json
        raise AssertionError("计数路径不应请求完整质检明细")

    def scan_write_protocol(self, payload_json: str) -> str:
        """计数路径不应请求完整写入协议明细。"""
        _ = payload_json
        raise AssertionError("计数路径不应请求完整写入协议明细")


class _MissingNativeContractModule:
    """模拟旧版 Rust 扩展：没有契约版本函数。"""


class _OldNativeContractModule:
    """模拟旧版 Rust 扩展：契约版本过低。"""

    def native_contract_version(self) -> int:
        """返回旧契约版本。"""
        return 1


def _sample_translation_item() -> TranslationItem:
    """构造原生适配层测试用译文条目。"""
    return TranslationItem(
        location_path="Items.json/1/name",
        item_type="short_text",
        original_lines=["薬草"],
        source_line_paths=["Items.json/1/name"],
        translation_lines=["草药"],
    )


def _import_missing_native_contract(_name: str) -> object:
    """返回缺少契约版本函数的旧扩展替身。"""
    return _MissingNativeContractModule()


def _import_old_native_contract(_name: str) -> object:
    """返回契约版本过低的旧扩展替身。"""
    return _OldNativeContractModule()


def test_native_quality_rejects_stale_native_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """质检入口不能让旧 Rust 扩展静默忽略新文本规则字段。"""
    monkeypatch.setattr(native_quality, "import_module", _import_missing_native_contract)
    with pytest.raises(RuntimeError, match="Rust 原生扩展版本过旧"):
        _ = native_quality.native_thread_count()

    monkeypatch.setattr(native_quality, "import_module", _import_old_native_contract)
    with pytest.raises(RuntimeError, match="Rust 原生扩展版本过旧"):
        _ = native_quality.native_thread_count()


def test_native_write_plan_rejects_stale_native_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """写回计划入口不能让旧 Rust 扩展继续执行旧质量 gate。"""
    monkeypatch.setattr(native_write_plan, "import_module", _import_missing_native_contract)
    with pytest.raises(RuntimeError, match="Rust 原生扩展版本过旧"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("."),
            content_root=Path("."),
            db_path=Path("game.db"),
            mode="write_back",
            confirm_font_overwrite=False,
        )

    monkeypatch.setattr(native_write_plan, "import_module", _import_old_native_contract)
    with pytest.raises(RuntimeError, match="Rust 原生扩展版本过旧"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("."),
            content_root=Path("."),
            db_path=Path("game.db"),
            mode="write_back",
            confirm_font_overwrite=False,
        )


def test_native_write_plan_reports_native_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rust 写回计划返回 error 状态时必须保留原始业务原因。"""
    fake_module = _FakeWritePlanModule(
        {
            "status": "error",
            "errors": [
                {
                    "code": "write_gate",
                    "message": "写进游戏文件前检查没通过",
                }
            ],
        }
    )

    def load_fake_module() -> native_write_plan.NativeWritePlanModule:
        """返回测试用写回计划模块。"""
        return cast(native_write_plan.NativeWritePlanModule, fake_module)

    monkeypatch.setattr(native_write_plan, "_load_native_module", load_fake_module)

    with pytest.raises(RuntimeError, match="写进游戏文件前检查没通过"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("game"),
            content_root=Path("game"),
            db_path=Path("game.db"),
            mode="rebuild_active_runtime",
            confirm_font_overwrite=False,
        )


def test_native_write_plan_rejects_target_path_outside_content_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python 适配层必须拦截 Rust 返回的越界目标路径。"""
    payload = _minimal_write_plan_payload()
    payload["files"] = [
        {
            "target_path": str(Path("outside") / "System.json"),
            "relative_path": "data/System.json",
            "content": "{}\n",
        }
    ]
    fake_module = _FakeWritePlanModule(payload)

    def load_fake_module() -> native_write_plan.NativeWritePlanModule:
        """返回测试用写回计划模块。"""
        return cast(native_write_plan.NativeWritePlanModule, fake_module)

    monkeypatch.setattr(native_write_plan, "_load_native_module", load_fake_module)

    with pytest.raises(RuntimeError, match="目标路径不在游戏内容目录内"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("game"),
            content_root=Path("game"),
            db_path=Path("game.db"),
            mode="rebuild_active_runtime",
            confirm_font_overwrite=False,
        )


def test_native_write_plan_requires_total_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rust 写回计划缺少 total 耗时时必须直接报错。"""
    payload = _minimal_write_plan_payload()
    payload["timings_ms"] = {}
    fake_module = _FakeWritePlanModule(payload)

    def load_fake_module() -> native_write_plan.NativeWritePlanModule:
        """返回测试用写回计划模块。"""
        return cast(native_write_plan.NativeWritePlanModule, fake_module)

    monkeypatch.setattr(native_write_plan, "_load_native_module", load_fake_module)

    with pytest.raises(TypeError, match="timings_ms.total 必须存在"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("game"),
            content_root=Path("game"),
            db_path=Path("game.db"),
            mode="rebuild_active_runtime",
            confirm_font_overwrite=False,
        )


def test_native_write_plan_rejects_bad_target_font_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rust 写回计划 target_font_name 类型错误时必须直接报错。"""
    payload = _minimal_write_plan_payload()
    summary = cast(dict[str, object], payload["summary"])
    summary["target_font_name"] = 123
    fake_module = _FakeWritePlanModule(payload)

    def load_fake_module() -> native_write_plan.NativeWritePlanModule:
        """返回测试用写回计划模块。"""
        return cast(native_write_plan.NativeWritePlanModule, fake_module)

    monkeypatch.setattr(native_write_plan, "_load_native_module", load_fake_module)

    with pytest.raises(TypeError, match="summary.target_font_name 必须是字符串或 null"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("game"),
            content_root=Path("game"),
            db_path=Path("game.db"),
            mode="rebuild_active_runtime",
            confirm_font_overwrite=False,
        )


def test_native_write_plan_parser_does_not_coerce_whole_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回计划解析只做字段级校验，避免递归复制文件内容大对象。"""
    content_root = tmp_path / "game"
    payload = _minimal_write_plan_payload()
    payload["files"] = [
        {
            "target_path": str(content_root / "data" / "System.json"),
            "relative_path": "data/System.json",
            "content": "x" * 1000,
        }
    ]
    fake_module = _FakeWritePlanModule(payload)

    def load_fake_module() -> native_write_plan.NativeWritePlanModule:
        """返回测试用写回计划模块。"""
        return cast(native_write_plan.NativeWritePlanModule, fake_module)

    monkeypatch.setattr(native_write_plan, "_load_native_module", load_fake_module)

    plan = native_write_plan.build_native_write_back_plan(
        game_path=content_root,
        content_root=content_root,
        db_path=tmp_path / "game.db",
        mode="rebuild_active_runtime",
        confirm_font_overwrite=False,
    )

    assert plan.files[0].content == "x" * 1000
    assert plan.files[0].target_path == content_root / "data" / "System.json"


def test_native_write_plan_accepts_content_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回计划可通过受信任 sidecar 文件返回大文本内容。"""
    content_root = tmp_path / "game"
    content_output_dir = tmp_path / "plan-content"
    content_output_dir.mkdir()
    sidecar_path = content_output_dir / "000000.txt"
    _ = sidecar_path.write_text("{\"gameTitle\":\"测试\"}\n", encoding="utf-8")
    payload = _minimal_write_plan_payload()
    payload["files"] = [
        {
            "target_path": str(content_root / "data" / "System.json"),
            "relative_path": "data/System.json",
            "content_path": str(sidecar_path),
        }
    ]
    fake_module = _FakeWritePlanModule(payload)

    def load_fake_module() -> native_write_plan.NativeWritePlanModule:
        """返回测试用写回计划模块。"""
        return cast(native_write_plan.NativeWritePlanModule, fake_module)

    monkeypatch.setattr(native_write_plan, "_load_native_module", load_fake_module)

    plan = native_write_plan.build_native_write_back_plan(
        game_path=content_root,
        content_root=content_root,
        db_path=tmp_path / "game.db",
        mode="rebuild_active_runtime",
        confirm_font_overwrite=False,
        setting_payload={"text_rules": {}},
        content_output_dir=content_output_dir,
    )

    assert fake_module.setting_payloads == [
        {
            "text_rules": {},
            "plan_content_output_dir": str(content_output_dir),
        }
    ]
    assert plan.files[0].content is None
    assert plan.files[0].content_path == sidecar_path.resolve(strict=False)


def test_native_write_plan_rejects_content_sidecar_outside_trusted_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rust 返回的 sidecar 文件必须位于本次临时输出目录内。"""
    content_root = tmp_path / "game"
    content_output_dir = tmp_path / "plan-content"
    content_output_dir.mkdir()
    outside_path = tmp_path / "outside.txt"
    _ = outside_path.write_text("{}", encoding="utf-8")
    payload = _minimal_write_plan_payload()
    payload["files"] = [
        {
            "target_path": str(content_root / "data" / "System.json"),
            "relative_path": "data/System.json",
            "content_path": str(outside_path),
        }
    ]
    fake_module = _FakeWritePlanModule(payload)

    def load_fake_module() -> native_write_plan.NativeWritePlanModule:
        """返回测试用写回计划模块。"""
        return cast(native_write_plan.NativeWritePlanModule, fake_module)

    monkeypatch.setattr(native_write_plan, "_load_native_module", load_fake_module)

    with pytest.raises(RuntimeError, match="content_path 不在临时输出目录内"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=content_root,
            content_root=content_root,
            db_path=tmp_path / "game.db",
            mode="rebuild_active_runtime",
            confirm_font_overwrite=False,
            content_output_dir=content_output_dir,
        )


def test_native_javascript_ast_requires_bool_has_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rust AST 结果 has_error 类型错误时必须直接报错。"""
    fake_module = _FakeJavaScriptAstModule({"has_error": "false", "spans": []})

    def load_fake_module() -> native_javascript_ast.NativeJavaScriptAstModule:
        """返回测试用 AST 模块。"""
        return cast(native_javascript_ast.NativeJavaScriptAstModule, fake_module)

    monkeypatch.setattr(native_javascript_ast, "_load_native_javascript_ast_module", load_fake_module)

    with pytest.raises(TypeError, match="has_error 必须是布尔值"):
        _ = native_javascript_ast.parse_native_javascript_string_spans("'文本'")


def test_native_javascript_ast_requires_ast_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rust AST 字符串节点缺少 ast_context 时必须直接报错。"""
    fake_module = _FakeJavaScriptAstModule(
        {
            "has_error": False,
            "spans": [
                {
                    "kind": "string",
                    "quote": "'",
                    "start_index": 0,
                    "end_index": 4,
                    "content_start_index": 1,
                    "content_end_index": 3,
                }
            ],
        }
    )

    def load_fake_module() -> native_javascript_ast.NativeJavaScriptAstModule:
        """返回测试用 AST 模块。"""
        return cast(native_javascript_ast.NativeJavaScriptAstModule, fake_module)

    monkeypatch.setattr(native_javascript_ast, "_load_native_javascript_ast_module", load_fake_module)

    with pytest.raises(TypeError, match="ast_context 必须存在"):
        _ = native_javascript_ast.parse_native_javascript_string_spans("'文本'")


def test_native_quality_counts_parse_count_only_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python 适配层应支持 Rust 只返回计数的轻量质检协议。"""
    fake_module = _FakeQualityModule(
        {
            "source_residual_count": 1,
            "text_structure_count": 2,
            "placeholder_risk_count": 3,
            "overwide_line_count": 4,
        },
        {"write_protocol_count": 5},
    )

    def load_fake_module() -> native_quality.NativeModule:
        """返回测试用质检模块。"""
        return cast(native_quality.NativeModule, cast(object, fake_module))

    monkeypatch.setattr(native_quality, "_load_native_module", load_fake_module)

    counts = native_quality.collect_native_quality_counts(
        items=[_sample_translation_item()],
        text_rules=TextRules.from_setting(TextRulesSetting()),
        source_residual_rules=[],
    )
    protocol_count = native_quality.count_native_write_protocol_issues(
        game_data=cast(JsonObject, {}),
        plugins_js=cast(JsonArray, []),
        items=[],
    )

    assert counts.source_residual_count == 1
    assert counts.text_structure_count == 2
    assert counts.placeholder_risk_count == 3
    assert counts.overwide_line_count == 4
    assert protocol_count == 5


def test_native_text_rules_payload_includes_source_copy_residual_policy() -> None:
    """英文源文复制残留配置必须进入 Rust 质检载荷。"""
    text_rules = TextRules.from_setting(build_text_rules_setting_for_language_profile("en"))

    payload = native_quality.build_native_text_rules_payload(text_rules)

    assert payload["source_residual_detection_profile"] == "english_source_copy"
    assert payload["english_source_copy_min_words"] == 4
    assert payload["english_source_copy_min_letters"] == 12
    assert payload["allowed_source_residual_terms"] == []


def test_native_quality_counts_reject_bad_count_types(monkeypatch: pytest.MonkeyPatch) -> None:
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

    def load_fake_module() -> native_quality.NativeModule:
        """返回测试用质检模块。"""
        return cast(native_quality.NativeModule, cast(object, fake_module))

    monkeypatch.setattr(native_quality, "_load_native_module", load_fake_module)

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
