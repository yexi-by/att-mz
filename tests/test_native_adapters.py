"""Rust 原生适配层协议校验测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast, override

import pytest

from app import (
    native_javascript_ast,
    native_note_tag_scan,
    native_quality,
    native_scope_index,
    native_structured_placeholder_scan,
    native_write_plan,
)
from app.config.schemas import TextRulesSetting
from app.language_profiles import build_text_rules_setting_for_language_profile
from app.persistence.sql import CURRENT_TEXT_FACT_CONTRACT_VERSION, current_schema_fingerprint, current_schema_sql
from app.rmmz.schema import GameData, TranslationItem
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules, ensure_json_object
from app.text_scope.models import WriteBackProbeError
from app.text_scope.write_probe import collect_write_back_probe_reasons


def test_placeholder_scanner_is_not_public_agent_toolkit_api() -> None:
    """占位符扫描器不能作为 agent_toolkit 包根公共 API 暴露。"""
    import app.agent_toolkit as agent_toolkit

    assert not hasattr(agent_toolkit, "scan_placeholder_candidates")


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

    def native_contract_version(self) -> int:
        """返回当前测试契约版本。"""
        return native_quality.NATIVE_CONTRACT_VERSION

    def parse_javascript_string_spans(self, payload_json: str) -> str:
        """返回测试预置的 AST 扫描结果。"""
        _ = payload_json
        return json.dumps(self._payload, ensure_ascii=False)

    def parse_javascript_string_spans_batch(self, payload_json: str) -> str:
        """返回测试预置的批量 AST 扫描结果。"""
        _ = payload_json
        return json.dumps({"files": [{"file_name": "test.js", **self._payload}]}, ensure_ascii=False)

    def collect_runtime_literal_issue_facts(self, payload_json: str) -> str:
        """返回测试预置的运行源码字符串风险事实。"""
        _ = payload_json
        return json.dumps(self._payload, ensure_ascii=False)


class _FakeJavaScriptAstModuleWithoutContract:
    """模拟缺少当前契约函数的 JS AST 扩展。"""

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


class _FakeJavaScriptAstModuleWithMismatchedContract(_FakeJavaScriptAstModule):
    """模拟契约版本不满足当前要求的 JS AST 扩展。"""

    @override
    def native_contract_version(self) -> int:
        """返回不满足当前要求的契约版本。"""
        return 1


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


class _FakeScopeIndexModule:
    """返回固定 Scope/Index JSON 的测试模块。"""

    _rule_candidates_payload: dict[str, object]
    _schema_fingerprint: str
    _storage_payload: dict[str, object]
    calls: int

    def __init__(
        self,
        rule_candidates_payload: dict[str, object],
        *,
        include_contract: bool = True,
        schema_fingerprint: str | None = None,
        storage_payload: dict[str, object] | None = None,
    ) -> None:
        """保存待返回的规则候选 JSON 对象。"""
        self._rule_candidates_payload = dict(rule_candidates_payload)
        if include_contract:
            _ = self._rule_candidates_payload.setdefault("schema_version", 1)
            _ = self._rule_candidates_payload.setdefault(
                "contract_versions",
                {
                    "rust_scope_facts": native_scope_index.RUST_SCOPE_FACTS_CONTRACT_VERSION,
                    "parser": native_scope_index.PARSER_CONTRACT_VERSION,
                    "source_branch": native_scope_index.SOURCE_BRANCH_CONTRACT_VERSION,
                    "text_fact_schema": CURRENT_TEXT_FACT_CONTRACT_VERSION,
                },
            )
            _ = self._rule_candidates_payload.setdefault("timings_ms", {})
            _ = self._rule_candidates_payload.setdefault("counters", {"candidate_count": 0})
        self._schema_fingerprint = schema_fingerprint or current_schema_fingerprint()
        self._storage_payload = storage_payload or {
            "status": "ok",
            "written_item_count": 0,
            "text_fact_count": 0,
            "render_part_count": 0,
            "scope_key": "tf-scope:fixture",
            "scope_hash": "0" * 64,
            "text_fact_schema_version": CURRENT_TEXT_FACT_CONTRACT_VERSION,
        }
        self.calls = 0

    def native_contract_version(self) -> int:
        """返回当前测试契约版本。"""
        return native_quality.NATIVE_CONTRACT_VERSION

    def build_scope_index(self, payload_json: str) -> str:
        """本测试不应调用范围索引构建。"""
        _ = payload_json
        raise AssertionError("规则候选适配测试不应构建 scope index")

    def scan_rule_candidates(self, payload_json: str) -> str:
        """返回测试预置的规则候选结果。"""
        _ = payload_json
        self.calls += 1
        return json.dumps(self._rule_candidates_payload, ensure_ascii=False)

    def evaluate_scope_gate(self, payload_json: str) -> str:
        """本测试不应调用范围门禁。"""
        _ = payload_json
        raise AssertionError("规则候选适配测试不应评估 scope gate")

    def native_schema_fingerprint(self) -> str:
        """返回测试预置的 schema 指纹。"""
        return self._schema_fingerprint

    def inspect_scope_index_storage(self, payload_json: str) -> str:
        """本测试不应检查 storage。"""
        _ = payload_json
        raise AssertionError("规则候选适配测试不应检查 storage")

    def write_scope_index_storage(self, payload_json: str) -> str:
        """返回测试预置的 storage 写入结果。"""
        _ = payload_json
        return json.dumps(self._storage_payload, ensure_ascii=False)

    def rebuild_scope_index_storage(self, payload_json: str) -> str:
        """返回测试预置的 storage 重建结果。"""
        _ = payload_json
        return json.dumps(self._storage_payload, ensure_ascii=False)


class _FakeRuntimeThreadModule(_FakeQualityModule):
    """记录 Python 传给 Rust 原生核心的线程配置。"""

    configured_values: list[int | None]

    def __init__(self) -> None:
        super().__init__(
            {
                "source_residual_count": 0,
                "text_structure_count": 0,
                "placeholder_risk_count": 0,
                "overwide_line_count": 0,
            },
            {"write_protocol_count": 0},
        )
        self.configured_values = []

    def configure_runtime_threads(self, rust_threads: int | None) -> None:
        """记录线程配置。"""
        self.configured_values.append(rust_threads)

    def native_thread_count(self) -> int:
        """返回当前记录的线程数。"""
        configured_value = self.configured_values[-1] if self.configured_values else None
        return configured_value if configured_value is not None else 7


class _MissingNativeContractModule:
    """模拟缺少当前契约函数的 Rust 扩展。"""


class _UnsupportedNativeContractModule:
    """模拟契约版本不满足当前要求的 Rust 扩展。"""

    def native_contract_version(self) -> int:
        """返回不满足当前要求的契约版本。"""
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


def _sample_game_data_for_note_tag_payload() -> GameData:
    """构造只满足 native Note 标签 payload 的测试 GameData。"""
    return cast(GameData, cast(object, SimpleNamespace(data={"Items.json": [{"note": "<desc:薬草>"}]})))


def _import_missing_native_contract(_name: str) -> object:
    """返回缺少契约版本函数的扩展替身。"""
    return _MissingNativeContractModule()


def _import_unsupported_native_contract(_name: str) -> object:
    """返回契约版本不满足当前要求的扩展替身。"""
    return _UnsupportedNativeContractModule()


def test_native_quality_requires_current_python_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """质检入口要求 Rust 扩展满足当前 Python 契约。"""
    monkeypatch.setattr(native_quality, "import_module", _import_missing_native_contract)
    with pytest.raises(RuntimeError, match="不满足当前 Python 契约"):
        _ = native_quality.native_thread_count()

    monkeypatch.setattr(native_quality, "import_module", _import_unsupported_native_contract)
    with pytest.raises(RuntimeError, match="不满足当前 Python 契约"):
        _ = native_quality.native_thread_count()


def test_native_write_plan_requires_current_python_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """写回计划入口要求 Rust 扩展满足当前 Python 契约。"""
    monkeypatch.setattr(native_write_plan, "import_module", _import_missing_native_contract)
    with pytest.raises(RuntimeError, match="不满足当前 Python 契约"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("."),
            content_root=Path("."),
            db_path=Path("game.db"),
            mode="write_back",
            confirm_font_overwrite=False,
        )

    monkeypatch.setattr(native_write_plan, "import_module", _import_unsupported_native_contract)
    with pytest.raises(RuntimeError, match="不满足当前 Python 契约"):
        _ = native_write_plan.build_native_write_back_plan(
            game_path=Path("."),
            content_root=Path("."),
            db_path=Path("game.db"),
            mode="write_back",
            confirm_font_overwrite=False,
        )


def test_native_javascript_ast_requires_current_python_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """JS AST 入口必须和其它 Rust 热路径一样要求当前原生契约。"""
    valid_payload: dict[str, object] = {"has_error": False, "spans": list[object]()}

    def import_missing_contract(_name: str) -> object:
        """返回缺少契约版本函数的 JS AST 扩展。"""
        return _FakeJavaScriptAstModuleWithoutContract(valid_payload)

    monkeypatch.setattr(native_javascript_ast, "import_module", import_missing_contract)
    with pytest.raises(RuntimeError, match="不满足当前 Python 契约"):
        _ = native_javascript_ast.parse_native_javascript_string_spans("'文本'")

    def import_old_contract(_name: str) -> object:
        """返回契约版本不满足当前要求的 JS AST 扩展。"""
        return _FakeJavaScriptAstModuleWithMismatchedContract(valid_payload)

    monkeypatch.setattr(native_javascript_ast, "import_module", import_old_contract)
    with pytest.raises(RuntimeError, match="不满足当前 Python 契约"):
        _ = native_javascript_ast.parse_native_javascript_string_spans("'文本'")


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


def test_native_javascript_ast_preserves_runtime_literal_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python 适配层必须保留 Rust AST 返回的运行审计分类事实。"""
    fake_module = _FakeJavaScriptAstModule(
        {
            "has_error": False,
            "spans": [
                {
                    "kind": "string",
                    "quote": "'",
                    "start_index": 0,
                    "end_index": 5,
                    "content_start_index": 1,
                    "content_end_index": 4,
                    "ast_context": {
                        "node_kind": "string",
                        "property_key": "",
                        "property_path": [],
                        "call_name": "",
                        "call_argument_index": None,
                        "return_function_name": "",
                        "assignment_name": "",
                    },
                    "literal_kind": "regex_pattern",
                    "audit_default_severity": "warning",
                }
            ],
        }
    )

    def load_fake_module() -> native_javascript_ast.NativeJavaScriptAstModule:
        """返回测试用 AST 模块。"""
        return cast(native_javascript_ast.NativeJavaScriptAstModule, fake_module)

    monkeypatch.setattr(native_javascript_ast, "_load_native_javascript_ast_module", load_fake_module)

    scan = native_javascript_ast.parse_native_javascript_string_spans("'\\\\w+'")

    assert scan.spans[0].literal_kind == "regex_pattern"
    assert scan.spans[0].audit_default_severity == "warning"


def test_native_javascript_ast_preserves_runtime_literal_issue_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python 适配层必须保留 Rust 返回的运行字符串风险事实。"""
    fake_module = _FakeJavaScriptAstModule(
        {
            "facts": [
                {
                    "id": "Plugin.js\nast:string:1:7:abcdef",
                    "literal_kind": "unknown",
                    "audit_default_severity": "warning",
                    "issue_codes": ["active_runtime_placeholder_risk"],
                    "placeholder_fragments": [r"\ii[1]"],
                    "control_code_hints": [
                        {
                            "original": r"\fb21st",
                            "candidate": r"\fb21",
                            "hint_kind": "possible_control_split",
                            "possible_split": {"control": r"\fb2", "tail": "1st"},
                            "message": "疑似控制符和后续数字或文本粘连",
                        }
                    ],
                }
            ]
        }
    )

    def load_fake_module() -> native_javascript_ast.NativeJavaScriptAstModule:
        """返回测试用 AST 模块。"""
        return cast(native_javascript_ast.NativeJavaScriptAstModule, fake_module)

    monkeypatch.setattr(native_javascript_ast, "_load_native_javascript_ast_module", load_fake_module)

    facts = native_javascript_ast.collect_native_runtime_literal_issue_facts(
        literals={
            "Plugin.js\nast:string:1:7:abcdef": (
                "\\\\ii[1]",
                r"\ii[1]",
                "unknown",
                "warning",
            )
        },
        text_rules=TextRules.from_setting(TextRulesSetting()),
    )

    fact = facts["Plugin.js\nast:string:1:7:abcdef"]
    assert fact.literal_kind == "unknown"
    assert fact.audit_default_severity == "warning"
    assert fact.issue_codes == ("active_runtime_placeholder_risk",)
    assert fact.placeholder_fragments == (r"\ii[1]",)
    assert ensure_json_object(fact.control_code_hints[0], "hint")["hint_kind"] == "possible_control_split"


def test_native_javascript_ast_requires_runtime_literal_issue_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rust 运行字符串风险事实缺少分类字段时，Python 适配层必须显式失败。"""
    fake_module = _FakeJavaScriptAstModule(
        {
            "facts": [
                {
                    "id": "Plugin.js\nast:string:1:7:abcdef",
                    "issue_codes": [],
                    "placeholder_fragments": [],
                    "control_code_hints": [],
                }
            ]
        }
    )

    def load_fake_module() -> native_javascript_ast.NativeJavaScriptAstModule:
        """返回测试用 AST 模块。"""
        return cast(native_javascript_ast.NativeJavaScriptAstModule, fake_module)

    monkeypatch.setattr(native_javascript_ast, "_load_native_javascript_ast_module", load_fake_module)

    with pytest.raises(RuntimeError, match="literal_kind"):
        _ = native_javascript_ast.collect_native_runtime_literal_issue_facts(
            literals={
                "Plugin.js\nast:string:1:7:abcdef": (
                    "\\\\ii[1]",
                    r"\ii[1]",
                    "unknown",
                    "warning",
                )
            },
            text_rules=TextRules.from_setting(TextRulesSetting()),
        )


def test_native_javascript_ast_reports_missing_runtime_literal_issue_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rust 运行字符串风险事实缺少必填字段时，Python 适配层必须给出可定位错误。"""
    literal_id = "Plugin.js\nast:string:1:7:abcdef"
    fake_module = _FakeJavaScriptAstModule(
        {
            "facts": [
                {
                    "id": literal_id,
                    "literal_kind": "unknown",
                    "audit_default_severity": "warning",
                    "placeholder_fragments": [],
                    "control_code_hints": [],
                }
            ]
        }
    )

    def load_fake_module() -> native_javascript_ast.NativeJavaScriptAstModule:
        """返回测试用 AST 模块。"""
        return cast(native_javascript_ast.NativeJavaScriptAstModule, fake_module)

    monkeypatch.setattr(native_javascript_ast, "_load_native_javascript_ast_module", load_fake_module)

    with pytest.raises(RuntimeError, match="issue_codes"):
        _ = native_javascript_ast.collect_native_runtime_literal_issue_facts(
            literals={
                literal_id: (
                    "\\\\ii[1]",
                    r"\ii[1]",
                    "unknown",
                    "warning",
                )
            },
            text_rules=TextRules.from_setting(TextRulesSetting()),
        )


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


def test_native_rule_candidates_requires_scan_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """contract 6 规则候选结果必须包含 scan_summary，不能由 Python 兜底吞掉。"""
    fake_module = _FakeScopeIndexModule(
        {
            "candidates": [],
            "candidate_summary": [],
        }
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    with pytest.raises(KeyError):
        _ = native_scope_index.scan_native_rule_candidates(cast(JsonObject, {"candidates": []}))


def test_native_rule_candidates_rejects_unsupported_schema_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """规则候选 adapter 必须拒绝不支持的 native schema_version。"""
    fake_module = _FakeScopeIndexModule(
        {
            "schema_version": 999,
            "candidates": [],
            "candidate_summary": [],
            "scan_summary": {},
            "timings_ms": {},
            "counters": {"candidate_count": 0},
        }
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    with pytest.raises(RuntimeError, match="schema_version"):
        _ = native_scope_index.scan_native_rule_candidates(cast(JsonObject, {"candidates": []}))


def test_native_rule_candidates_requires_contract_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """规则候选 adapter 必须保留 native contract 计时和计数字段。"""
    fake_module = _FakeScopeIndexModule(
        {
            "schema_version": 1,
            "candidates": [],
            "candidate_summary": [],
            "scan_summary": {},
            "counters": {"candidate_count": 0},
        },
        include_contract=False,
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    with pytest.raises(KeyError):
        _ = native_scope_index.scan_native_rule_candidates(cast(JsonObject, {"candidates": []}))


def test_shared_schema_fingerprint_requires_current_text_fact_tables_and_indexes() -> None:
    """共享 schema 指纹必须覆盖 当前文本事实 表和关键索引。"""
    schema_sql = current_schema_sql()
    for marker in (
        "text_facts",
        "text_fact_render_parts",
        "text_fact_domain_payloads",
        "text_fact_scope",
        "idx_text_facts_domain_location",
        "idx_text_facts_domain_source_file",
        "idx_text_facts_selector",
        "idx_text_facts_visible_hash",
        "idx_text_facts_translatable_hash",
        "idx_text_facts_scope_key",
    ):
        assert marker in schema_sql
    assert len(current_schema_fingerprint()) == 64


def test_native_schema_fingerprint_rejects_mismatched_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python adapter 不能接受不满足当前要求的 schema 指纹。"""
    fake_module = _FakeScopeIndexModule(
        {
            "candidates": [],
            "candidate_summary": [],
            "scan_summary": {},
        },
        schema_fingerprint="invalid-schema-fingerprint",
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    with pytest.raises(RuntimeError, match="rebuild-text-index"):
        _ = native_scope_index.native_schema_fingerprint()


def test_native_storage_contract_error_names_rebuild_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """storage 返回不满足当前 text fact 契约的结果时提示重建当前索引。"""
    fake_module = _FakeScopeIndexModule(
        {
            "candidates": [],
            "candidate_summary": [],
            "scan_summary": {},
        },
        storage_payload={
            "status": "ok",
            "written_item_count": 0,
            "text_fact_count": 0,
            "render_part_count": 0,
            "scope_key": "invalid-scope",
            "scope_hash": "0" * 64,
            "text_fact_schema_version": CURRENT_TEXT_FACT_CONTRACT_VERSION - 1,
        },
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    with pytest.raises(RuntimeError) as error_info:
        _ = native_scope_index.rebuild_native_scope_index_storage(cast(JsonObject, {}))

    message = str(error_info.value)
    assert "影响命令: rebuild-text-index" in message
    assert "重新构建 Rust 原生扩展或更新发行包" in message
    assert "然后再运行 rebuild-text-index" in message


def test_write_probe_requires_precomputed_plugin_source_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码写回探针必须由当前预计算扫描提供上下文。"""

    def successful_native_probe(
        *,
        game_data: object,
        plugins_js: list[object],
        items: list[TranslationItem],
    ) -> list[object]:
        """模拟普通写入协议探针通过。"""
        _ = (game_data, plugins_js, items)
        return []

    def forbidden_runtime_scan(*args: object, **kwargs: object) -> object:
        """生产写回探针不应再临时扫描插件源码。"""
        _ = (args, kwargs)
        raise AssertionError("当前写回探针不应临时扫描插件源码")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        successful_native_probe,
    )
    monkeypatch.setattr(
        "app.text_scope.write_probe.scan_plugin_source_runtime_files_text_strict",
        forbidden_runtime_scan,
        raising=False,
    )
    game_data = cast(
        GameData,
        cast(
            object,
            SimpleNamespace(
                data={},
                plugins_js=[],
                plugin_source_files={"Task9.js": "Window_Base.prototype.drawText('原文', 0, 0, 320);"},
            ),
        ),
    )
    item = TranslationItem(
        location_path="js/plugins/Task9.js/ast:string:1:36:task9",
        item_type="short_text",
        original_lines=["原文"],
        source_line_paths=["js/plugins/Task9.js/ast:string:1:36:task9"],
    )

    with pytest.raises(WriteBackProbeError, match="rebuild-text-index"):
        _ = collect_write_back_probe_reasons(
            game_data=game_data,
            active_items=[item],
            plugin_source_scan=None,
        )


def test_native_structured_placeholder_adapter_preserves_contract_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """结构化占位符 adapter 必须保留 native coverage contract 字段。"""
    fake_module = _FakeScopeIndexModule(
        {
            "candidates": [],
            "candidate_summary": [{"domain": "structured_placeholders", "candidate_count": 1}],
            "scan_summary": {
                "structured_placeholders": {
                    "candidates": [
                        {
                            "location_path": "Map001.json/1/0",
                            "location_paths": ["Map001.json/1/0"],
                            "line_number": 1,
                            "candidate": "<Face:Bob>",
                            "text": "<Face:Bob>",
                            "range": [0, 10],
                            "covered": True,
                            "covered_by": "custom_placeholder",
                            "matching_rules": [],
                            "candidate_kind": "structured_shell",
                        }
                    ],
                    "scope_hash": "1" * 64,
                }
            },
        }
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    details = native_structured_placeholder_scan.collect_native_structured_placeholder_candidate_details_from_entries(
        entries=[("Map001.json/1/0", ["<Face:Bob>"])],
        text_rules=TextRules.from_setting(TextRulesSetting()),
    )

    assert details == [
        {
            "location_path": "Map001.json/1/0",
            "location_paths": ["Map001.json/1/0"],
            "line_number": 1,
            "candidate": "<Face:Bob>",
            "text": "<Face:Bob>",
            "range": [0, 10],
            "covered": True,
            "covered_by": "custom_placeholder",
            "matching_rules": [],
            "candidate_kind": "structured_shell",
        }
    ]


def test_native_structured_placeholder_adapter_requires_requested_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """请求结构化候选时缺少 structured_placeholders 摘要必须显式失败。"""
    fake_module = _FakeScopeIndexModule(
        {
            "candidates": [],
            "candidate_summary": [],
            "scan_summary": {},
        }
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    with pytest.raises(RuntimeError, match="structured_placeholders"):
        _ = native_structured_placeholder_scan.collect_native_structured_placeholder_candidate_details_from_entries(
            entries=[("Map001.json/1/0", ["<Face:Bob>"])],
            text_rules=TextRules.from_setting(TextRulesSetting()),
        )


def test_native_structured_placeholder_adapter_skips_empty_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空文本范围没有 native 扫描工作项，应直接返回空结构化候选。"""

    def forbidden_scan_native_rule_candidates(_payload: JsonObject) -> None:
        raise AssertionError("empty structured placeholder input should not call native scan")

    monkeypatch.setattr(
        native_structured_placeholder_scan,
        "scan_native_rule_candidates",
        forbidden_scan_native_rule_candidates,
    )
    text_rules = TextRules.from_setting(TextRulesSetting())

    assert (
        native_structured_placeholder_scan.collect_native_structured_placeholder_candidate_details(
            translation_data_map={},
            text_rules=text_rules,
        )
        == []
    )
    assert (
        native_structured_placeholder_scan.collect_native_structured_placeholder_candidate_details_from_entries(
            entries=[],
            text_rules=text_rules,
        )
        == []
    )


def test_collect_native_note_tag_source_details_returns_source_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签来源存在 helper 必须返回独立 source_details 摘要。"""
    fake_module = _FakeScopeIndexModule(
        {
            "candidates": [],
            "candidate_summary": [],
            "scan_summary": {
                "note_tags": {
                    "source_details": [
                        {
                            "file_name": "Items.json",
                            "location_prefix": "Items.json/1",
                        }
                    ]
                }
            },
        }
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    source_details = native_note_tag_scan.collect_native_note_tag_source_details(
        game_data=_sample_game_data_for_note_tag_payload(),
        text_rules=TextRules.from_setting(TextRulesSetting()),
    )

    assert source_details == [
        {
            "file_name": "Items.json",
            "location_prefix": "Items.json/1",
        }
    ]


def test_collect_native_note_tag_source_details_requires_source_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """native Note 标签结果缺少 source_details 时不能静默当作无来源。"""
    fake_module = _FakeScopeIndexModule(
        {
            "candidates": [],
            "candidate_summary": [],
            "scan_summary": {"note_tags": {}},
        }
    )

    def load_fake_module() -> native_scope_index.NativeScopeIndexModule:
        """返回测试用 Scope/Index 模块。"""
        return cast(native_scope_index.NativeScopeIndexModule, cast(object, fake_module))

    monkeypatch.setattr(native_scope_index, "_load_native_scope_index_module", load_fake_module)

    with pytest.raises(RuntimeError, match="source_details 缺失"):
        _ = native_note_tag_scan.collect_native_note_tag_source_details(
            game_data=_sample_game_data_for_note_tag_payload(),
            text_rules=TextRules.from_setting(TextRulesSetting()),
        )


def test_native_runtime_thread_config_maps_auto_and_positive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python adapter 必须把 auto 转成 None，正整数原样传给 Rust。"""
    fake_module = _FakeRuntimeThreadModule()

    def load_fake_module() -> native_quality.NativeModule:
        """返回测试用原生运行时模块。"""
        return cast(native_quality.NativeModule, cast(object, fake_module))

    monkeypatch.setattr(native_quality, "_load_native_module", load_fake_module)

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
