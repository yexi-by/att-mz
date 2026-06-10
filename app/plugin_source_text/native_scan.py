"""Rust-derived 插件源码候选事实适配。"""

from __future__ import annotations

from app.native_scope_index import (
    PARSER_CONTRACT_VERSION,
    RUST_SCOPE_FACTS_CONTRACT_VERSION,
    build_native_plugin_source_candidates_payload,
    scan_native_rule_candidates,
)
from app.plugin_text import extract_plugin_name
from app.rmmz.schema import GameData, PluginSourceTextRuleRecord
from app.rmmz.text_rules import JsonArray, JsonObject, JsonValue, TextRules, ensure_json_array, ensure_json_object

from .models import (
    PluginSourceCandidate,
    PluginSourceFileScan,
    PluginSourceReviewSummary,
    PluginSourceRisk,
    PluginSourceScan,
    PluginSourceSelectorFact,
    PluginSourceStaleReason,
)
from .scanner import build_plugin_source_file_hash

PLUGIN_SOURCE_RUNTIME_SCAN_RUST_CONTRACT_VERSION = RUST_SCOPE_FACTS_CONTRACT_VERSION
PLUGIN_SOURCE_RUNTIME_SCAN_PARSER_CONTRACT_VERSION = PARSER_CONTRACT_VERSION


def build_native_plugin_source_risk_report(*, game_data: GameData, text_rules: TextRules) -> JsonObject:
    """用 Rust 候选入口构造 scan-plugin-source-text 的轻量风险报告。"""
    return build_native_plugin_source_risk_report_from_inputs(
        plugins_js=game_data.plugins_js,
        plugin_source_files=game_data.plugin_source_files,
        plugin_source_read_errors=game_data.plugin_source_read_errors,
        text_rules=text_rules,
    )


def build_native_plugin_source_risk_report_from_inputs(
    *,
    plugins_js: list[dict[str, JsonValue]],
    plugin_source_files: dict[str, str],
    plugin_source_read_errors: dict[str, str],
    text_rules: TextRules,
) -> JsonObject:
    """用轻量插件源码输入构造 scan-plugin-source-text 风险报告。"""
    enabled_plugin_files = _enabled_plugin_source_file_names_from_plugins(plugins_js)
    if not plugin_source_files:
        empty_ast_map = _empty_native_plugin_source_ast_map_payload(
            enabled_plugin_files=enabled_plugin_files,
            read_error_file_count=len(plugin_source_read_errors),
        )
        return native_plugin_source_risk_report_from_ast_map(empty_ast_map)
    native_result = scan_native_rule_candidates(
        build_native_plugin_source_candidates_payload(
            plugin_source_files=plugin_source_files,
            enabled_plugin_files=enabled_plugin_files,
            text_rules=text_rules,
            plugin_source_read_error_file_count=len(plugin_source_read_errors),
        )
    )
    plugin_summary = ensure_json_object(
        native_result.scan_summary["plugin_source"],
        "native_rule_candidates_result.scan_summary.plugin_source",
    )
    raw_candidates = [
        ensure_json_object(candidate, f"native_rule_candidates_result.candidates[{index}]")
        for index, candidate in enumerate(native_result.candidates)
    ]
    _assert_native_plugin_source_summary_counts(raw_candidates=raw_candidates, plugin_summary=plugin_summary)

    candidates = [
        candidate
        for index, candidate in enumerate(raw_candidates)
        if _native_plugin_source_candidate_should_translate(candidate, text_rules, index)
    ]
    active_candidate_count = 0
    for index, candidate in enumerate(candidates):
        label = f"native_rule_candidates_result.candidates[{index}]"
        if not _json_bool(candidate, "active", label):
            continue
        active_candidate_count += 1
    syntax_errors = ensure_json_array(
        plugin_summary["syntax_errors"],
        "native_rule_candidates_result.scan_summary.plugin_source.syntax_errors",
    )
    risk = _native_plugin_source_risk_summary(plugin_summary)
    enabled_plugin_files_json: JsonArray = [file_name for file_name in sorted(enabled_plugin_files)]
    return {
        "risk": risk,
        "enabled_plugin_files": enabled_plugin_files_json,
        "candidate_count": len(candidates),
        "active_candidate_count": active_candidate_count,
        "syntax_errors": syntax_errors,
    }


def build_native_plugin_source_ast_map_payload(*, game_data: GameData, text_rules: TextRules) -> JsonObject:
    """用 Rust 候选入口构造完整插件源码 AST 地图。"""
    return build_native_plugin_source_ast_map_payload_from_inputs(
        plugins_js=game_data.plugins_js,
        plugin_source_files=game_data.plugin_source_files,
        plugin_source_read_errors=game_data.plugin_source_read_errors,
        text_rules=text_rules,
    )


def build_native_plugin_source_ast_map_payload_from_inputs(
    *,
    plugins_js: list[dict[str, JsonValue]],
    plugin_source_files: dict[str, str],
    plugin_source_read_errors: dict[str, str],
    text_rules: TextRules,
) -> JsonObject:
    """用轻量插件源码输入构造完整插件源码 AST 地图。"""
    payload, _risk_report = build_native_plugin_source_ast_map_payload_and_risk_report_from_inputs(
        plugins_js=plugins_js,
        plugin_source_files=plugin_source_files,
        plugin_source_read_errors=plugin_source_read_errors,
        text_rules=text_rules,
    )
    return payload


def build_native_plugin_source_ast_map_payload_and_risk_report_from_inputs(
    *,
    plugins_js: list[dict[str, JsonValue]],
    plugin_source_files: dict[str, str],
    plugin_source_read_errors: dict[str, str],
    text_rules: TextRules,
) -> tuple[JsonObject, JsonObject]:
    """用同一次 native 结果构造 AST map 和轻量风险报告。"""
    enabled_plugin_files = _enabled_plugin_source_file_names_from_plugins(plugins_js)
    if not plugin_source_files:
        payload = _empty_native_plugin_source_ast_map_payload(
            enabled_plugin_files=enabled_plugin_files,
            read_error_file_count=len(plugin_source_read_errors),
        )
        return payload, native_plugin_source_risk_report_from_ast_map(payload)
    native_result = scan_native_rule_candidates(
        build_native_plugin_source_candidates_payload(
            plugin_source_files=plugin_source_files,
            enabled_plugin_files=enabled_plugin_files,
            text_rules=text_rules,
            plugin_source_read_error_file_count=len(plugin_source_read_errors),
        )
    )
    plugin_summary = ensure_json_object(
        native_result.scan_summary["plugin_source"],
        "native_rule_candidates_result.scan_summary.plugin_source",
    )
    raw_candidates = [
        ensure_json_object(candidate, f"native_rule_candidates_result.candidates[{index}]")
        for index, candidate in enumerate(native_result.candidates)
    ]
    _assert_native_plugin_source_summary_counts(raw_candidates=raw_candidates, plugin_summary=plugin_summary)

    syntax_errors = ensure_json_array(
        plugin_summary["syntax_errors"],
        "native_rule_candidates_result.scan_summary.plugin_source.syntax_errors",
    )
    syntax_error_files = _native_plugin_source_syntax_error_files(syntax_errors)
    candidates_by_file: dict[str, list[JsonObject]] = {
        file_name: []
        for file_name in sorted(plugin_source_files)
        if file_name not in syntax_error_files
    }
    active_candidate_count = 0
    for index, candidate in enumerate(raw_candidates):
        if not _native_plugin_source_candidate_should_translate(candidate, text_rules, index):
            continue
        label = f"native_rule_candidates_result.candidates[{index}]"
        if _json_bool(candidate, "active", label):
            active_candidate_count += 1
        file_name = _native_plugin_source_candidate_file(candidate, label)
        file_candidates = candidates_by_file.get(file_name)
        if file_candidates is None:
            raise RuntimeError(f"Rust 插件源码候选引用了未知文件: {file_name}")
        file_candidates.append(_native_plugin_source_candidate_to_ast_map_json(candidate, label))
    file_payloads: list[JsonObject] = [
            _native_plugin_source_file_ast_map_json(
                file_name=file_name,
                source=plugin_source_files[file_name],
                active=file_name in enabled_plugin_files,
                candidates=candidates,
            )
        for file_name, candidates in candidates_by_file.items()
    ]
    candidate_count = sum(len(candidates) for candidates in candidates_by_file.values())
    risk = _native_plugin_source_risk_summary(plugin_summary)
    enabled_plugin_files_json: JsonArray = [file_name for file_name in sorted(enabled_plugin_files)]
    files_json: JsonArray = [file_payload for file_payload in file_payloads]
    payload: JsonObject = {
        "risk": risk,
        "enabled_plugin_files": enabled_plugin_files_json,
        "candidate_count": candidate_count,
        "syntax_errors": syntax_errors,
        "files": files_json,
    }
    risk_report: JsonObject = {
        "risk": risk,
        "enabled_plugin_files": enabled_plugin_files_json,
        "candidate_count": candidate_count,
        "active_candidate_count": active_candidate_count,
        "syntax_errors": syntax_errors,
    }
    return payload, risk_report


def build_native_plugin_source_scan(
    *,
    game_data: GameData,
    text_rules: TextRules,
    rule_records: list[PluginSourceTextRuleRecord] | None = None,
) -> PluginSourceScan:
    """用 Rust 候选入口构造当前插件源码规则扫描对象。"""
    enabled_plugin_files = _enabled_plugin_source_file_names(game_data)
    if not game_data.plugin_source_files:
        risk_json = _native_plugin_source_risk_from_file_payloads(
            [],
            read_error_file_count=len(game_data.plugin_source_read_errors),
            scanned_file_count=0,
            ignored_file_count=0,
            syntax_error_file_count=0,
        )
        return PluginSourceScan(
            risk=_plugin_source_risk_from_json(risk_json),
            files=(),
            candidates=(),
            selector_facts=(),
            review_summary=_empty_plugin_source_review_summary(),
            scope_hash="",
            enabled_plugin_files=enabled_plugin_files,
            syntax_errors={},
        )
    native_result = scan_native_rule_candidates(
        build_native_plugin_source_candidates_payload(
            plugin_source_files=game_data.plugin_source_files,
            enabled_plugin_files=enabled_plugin_files,
            text_rules=text_rules,
            plugin_source_text_rules=rule_records,
            plugin_source_read_error_file_count=len(game_data.plugin_source_read_errors),
        )
    )
    plugin_summary = ensure_json_object(
        native_result.scan_summary["plugin_source"],
        "native_rule_candidates_result.scan_summary.plugin_source",
    )
    raw_candidates = [
        ensure_json_object(candidate, f"native_rule_candidates_result.candidates[{index}]")
        for index, candidate in enumerate(native_result.candidates)
    ]
    _assert_native_plugin_source_summary_counts(raw_candidates=raw_candidates, plugin_summary=plugin_summary)
    selector_facts = _native_plugin_source_selector_facts(plugin_summary)
    review_summary = _native_plugin_source_review_summary(plugin_summary)
    scope_hash = _json_str(plugin_summary, "scope_hash", "native_rule_candidates_result.scan_summary.plugin_source")

    syntax_errors = ensure_json_array(
        plugin_summary["syntax_errors"],
        "native_rule_candidates_result.scan_summary.plugin_source.syntax_errors",
    )
    syntax_error_map = _native_plugin_source_syntax_error_map(syntax_errors)
    candidates_by_file: dict[str, list[PluginSourceCandidate]] = {
        file_name: []
        for file_name in sorted(game_data.plugin_source_files)
        if file_name not in syntax_error_map
    }
    for index, candidate in enumerate(raw_candidates):
        if not _native_plugin_source_candidate_should_translate(candidate, text_rules, index):
            continue
        label = f"native_rule_candidates_result.candidates[{index}]"
        file_name = _native_plugin_source_candidate_file(candidate, label)
        file_candidates = candidates_by_file.get(file_name)
        if file_candidates is None:
            raise RuntimeError(f"Rust 插件源码候选引用了未知文件: {file_name}")
        file_candidates.append(_native_plugin_source_candidate_to_scan_candidate(candidate, label))

    file_scans: list[PluginSourceFileScan] = []
    all_candidates: list[PluginSourceCandidate] = []
    for file_name, candidates in candidates_by_file.items():
        active_candidates = [candidate for candidate in candidates if candidate.active]
        strong_count = sum(1 for candidate in active_candidates if candidate.confidence == "strong")
        medium_count = sum(1 for candidate in active_candidates if candidate.confidence == "medium")
        file_scan = PluginSourceFileScan(
            file_name=file_name,
            file_hash=build_plugin_source_file_hash(game_data.plugin_source_files[file_name]),
            active=file_name in enabled_plugin_files,
            candidates=tuple(candidates),
            strong_context_text_count=strong_count,
            medium_confidence_text_count=medium_count,
            file_score=strong_count * 3 + medium_count,
        )
        file_scans.append(file_scan)
        all_candidates.extend(candidates)

    risk_json = _native_plugin_source_risk_summary(plugin_summary)
    return PluginSourceScan(
        risk=_plugin_source_risk_from_json(risk_json),
        files=tuple(file_scans),
        candidates=tuple(all_candidates),
        selector_facts=tuple(selector_facts),
        review_summary=review_summary,
        scope_hash=scope_hash,
        enabled_plugin_files=enabled_plugin_files,
        syntax_errors=syntax_error_map,
    )


def native_plugin_source_risk_report_from_ast_map(ast_map: JsonObject) -> JsonObject:
    """从完整 AST map 派生轻量风险报告。"""
    files = ensure_json_array(ast_map["files"], "plugin-source-ast-map.files")
    active_candidate_count = 0
    for file_index, raw_file in enumerate(files):
        file_payload = ensure_json_object(raw_file, f"plugin-source-ast-map.files[{file_index}]")
        candidates = ensure_json_array(file_payload["candidates"], f"plugin-source-ast-map.files[{file_index}].candidates")
        for candidate_index, raw_candidate in enumerate(candidates):
            candidate = ensure_json_object(
                raw_candidate,
                f"plugin-source-ast-map.files[{file_index}].candidates[{candidate_index}]",
            )
            if _json_bool(candidate, "active", f"plugin-source-ast-map.files[{file_index}].candidates[{candidate_index}]"):
                active_candidate_count += 1
    return {
        "risk": ensure_json_object(ast_map["risk"], "plugin-source-ast-map.risk"),
        "enabled_plugin_files": ensure_json_array(
            ast_map["enabled_plugin_files"],
            "plugin-source-ast-map.enabled_plugin_files",
        ),
        "candidate_count": _summary_int(ast_map, "candidate_count"),
        "active_candidate_count": active_candidate_count,
        "syntax_errors": ensure_json_array(ast_map["syntax_errors"], "plugin-source-ast-map.syntax_errors"),
    }


def native_plugin_source_risk_report_from_scan(scan: PluginSourceScan) -> JsonObject:
    """从 Rust-derived PluginSourceScan 派生轻量风险报告。"""
    enabled_plugin_files_json: JsonArray = [file_name for file_name in sorted(scan.enabled_plugin_files)]
    syntax_errors: JsonArray = [
        {
            "file": file_name,
            "active": file_name in scan.enabled_plugin_files,
            "syntax_error": error,
        }
        for file_name, error in sorted(scan.syntax_errors.items())
    ]
    return {
        "risk": scan.risk.to_json_object(),
        "enabled_plugin_files": enabled_plugin_files_json,
        "candidate_count": len(scan.candidates),
        "active_candidate_count": sum(1 for candidate in scan.candidates if candidate.active),
        "syntax_errors": syntax_errors,
    }


def _enabled_plugin_source_file_names(game_data: GameData) -> frozenset[str]:
    """返回 plugins.js 中启用的直接插件源码文件名。"""
    return _enabled_plugin_source_file_names_from_plugins(game_data.plugins_js)


def _enabled_plugin_source_file_names_from_plugins(plugins_js: list[dict[str, JsonValue]]) -> frozenset[str]:
    """返回 plugins.js 中启用的直接插件源码文件名。"""
    file_names: set[str] = set()
    for plugin_index, plugin in enumerate(plugins_js):
        if plugin.get("status") is not True:
            continue
        plugin_name = extract_plugin_name(plugin, plugin_index).strip()
        if not plugin_name:
            continue
        file_names.add(f"{plugin_name}.js")
    return frozenset(file_names)


def _assert_native_plugin_source_summary_counts(
    *,
    raw_candidates: list[JsonObject],
    plugin_summary: JsonObject,
) -> None:
    """确认 Rust 插件源码候选列表和摘要没有漂移。"""
    raw_candidate_count = len(raw_candidates)
    summary_candidate_count = _summary_int(plugin_summary, "candidate_count")
    if summary_candidate_count != raw_candidate_count:
        raise RuntimeError("Rust 插件源码候选数与扫描摘要不一致")
    raw_active_candidate_count = sum(
        1
        for index, candidate in enumerate(raw_candidates)
        if _json_bool(candidate, "active", f"native_rule_candidates_result.candidates[{index}]")
    )
    summary_active_candidate_count = _summary_int(plugin_summary, "active_candidate_count")
    if summary_active_candidate_count != raw_active_candidate_count:
        raise RuntimeError("Rust 插件源码启用候选数与扫描摘要不一致")


def _native_plugin_source_risk_summary(plugin_summary: JsonObject) -> JsonObject:
    """读取 Rust 插件源码风险摘要。"""
    return ensure_json_object(
        plugin_summary["risk_summary"],
        "native_rule_candidates_result.scan_summary.plugin_source.risk_summary",
    )


def _native_plugin_source_selector_facts(plugin_summary: JsonObject) -> list[PluginSourceSelectorFact]:
    """读取 Rust 插件源码 selector facts。"""
    raw_facts = ensure_json_array(
        plugin_summary["selector_facts"],
        "native_rule_candidates_result.scan_summary.plugin_source.selector_facts",
    )
    facts: list[PluginSourceSelectorFact] = []
    for index, raw_fact in enumerate(raw_facts):
        label = f"native_rule_candidates_result.scan_summary.plugin_source.selector_facts[{index}]"
        fact = ensure_json_object(raw_fact, label)
        raw_stale_reason = fact.get("stale_reason")
        stale_reason: PluginSourceStaleReason | None = None
        if raw_stale_reason is not None:
            stale_label = f"{label}.stale_reason"
            stale = ensure_json_object(raw_stale_reason, stale_label)
            stale_reason = PluginSourceStaleReason(
                code=_json_str(stale, "code", stale_label),
                message=_json_str(stale, "message", stale_label),
            )
        facts.append(
            PluginSourceSelectorFact(
                file_name=_json_str(fact, "file_name", label),
                selector=_json_str(fact, "selector", label),
                role=_json_str(fact, "role", label),
                active=_json_bool(fact, "active", label),
                file_hash=_json_str(fact, "file_hash", label),
                source_text_hash=_json_str(fact, "source_text_hash", label),
                stale_reason=stale_reason,
            )
        )
    return facts


def _native_plugin_source_review_summary(plugin_summary: JsonObject) -> PluginSourceReviewSummary:
    """读取 Rust 插件源码审查覆盖摘要。"""
    summary = ensure_json_object(
        plugin_summary["review_summary"],
        "native_rule_candidates_result.scan_summary.plugin_source.review_summary",
    )
    return PluginSourceReviewSummary(
        total_selector_count=_summary_int(summary, "total_selector_count"),
        translated_selector_count=_summary_int(summary, "translated_selector_count"),
        excluded_selector_count=_summary_int(summary, "excluded_selector_count"),
        filtered_selector_count=_summary_int(summary, "filtered_selector_count"),
        reviewed_selector_count=_summary_int(summary, "reviewed_selector_count"),
        stale_selector_count=_summary_int(summary, "stale_selector_count"),
        active_candidate_count=_summary_int(summary, "active_candidate_count"),
        unreviewed_selector_count=_summary_int(summary, "unreviewed_selector_count"),
        review_required=_json_bool(summary, "review_required", "plugin-source-review-summary"),
    )


def _empty_plugin_source_review_summary() -> PluginSourceReviewSummary:
    """构造无插件源码文件时的空审查摘要。"""
    return PluginSourceReviewSummary(
        total_selector_count=0,
        translated_selector_count=0,
        excluded_selector_count=0,
        filtered_selector_count=0,
        reviewed_selector_count=0,
        stale_selector_count=0,
        active_candidate_count=0,
        unreviewed_selector_count=0,
        review_required=False,
    )


def _native_plugin_source_risk_from_file_payloads(
    files: list[JsonObject],
    *,
    read_error_file_count: int,
    scanned_file_count: int,
    ignored_file_count: int,
    syntax_error_file_count: int,
) -> JsonObject:
    """按当前风险阈值从 AST map 文件摘要构造风险对象。"""
    active_files = [
        file_payload
        for file_payload in files
        if _json_bool(file_payload, "active", "plugin-source-ast-map.files[]")
    ]
    strong_total = sum(_summary_int(file_payload, "strong_context_text_count") for file_payload in active_files)
    medium_total = sum(_summary_int(file_payload, "medium_confidence_text_count") for file_payload in active_files)
    risk_score = strong_total * 3 + medium_total
    files_score_ge_250 = sum(1 for file_payload in active_files if _summary_int(file_payload, "file_score") >= 250)
    max_file_score = max((_summary_int(file_payload, "file_score") for file_payload in active_files), default=0)
    high_risk = (
        strong_total >= 300
        or risk_score >= 2000
        or files_score_ge_250 >= 3
        or any(
            _summary_int(file_payload, "file_score") >= 300
            and _summary_int(file_payload, "strong_context_text_count") >= 80
            for file_payload in active_files
        )
    )
    thresholds: JsonObject = {
        "strong_context_text_count": 300,
        "risk_score": 2000,
        "files_score_ge_250": 3,
        "single_file_score": 300,
        "single_file_strong_context_text_count": 80,
    }
    return {
        "high_risk": high_risk,
        "risk_score": risk_score,
        "strong_context_text_count": strong_total,
        "medium_confidence_text_count": medium_total,
        "scanned_file_count": scanned_file_count,
        "ignored_file_count": ignored_file_count,
        "read_error_file_count": read_error_file_count,
        "syntax_error_file_count": syntax_error_file_count,
        "files_score_ge_250": files_score_ge_250,
        "max_file_score": max_file_score,
        "thresholds": thresholds,
    }


def _plugin_source_risk_from_json(risk: JsonObject) -> PluginSourceRisk:
    """把 Rust 风险 JSON 转换为当前插件源码风险对象。"""
    return PluginSourceRisk(
        high_risk=_json_bool(risk, "high_risk", "plugin-source-risk-report.risk"),
        risk_score=_summary_int(risk, "risk_score"),
        strong_context_text_count=_summary_int(risk, "strong_context_text_count"),
        medium_confidence_text_count=_summary_int(risk, "medium_confidence_text_count"),
        scanned_file_count=_summary_int(risk, "scanned_file_count"),
        ignored_file_count=_summary_int(risk, "ignored_file_count"),
        read_error_file_count=_summary_int(risk, "read_error_file_count"),
        syntax_error_file_count=_summary_int(risk, "syntax_error_file_count"),
        files_score_ge_250=_summary_int(risk, "files_score_ge_250"),
        max_file_score=_summary_int(risk, "max_file_score"),
    )


def _empty_native_plugin_source_ast_map_payload(
    *,
    enabled_plugin_files: frozenset[str],
    read_error_file_count: int,
) -> JsonObject:
    """构造没有可读插件源码文件时的当前空 AST 地图。"""
    risk = _native_plugin_source_risk_from_file_payloads(
        [],
        read_error_file_count=read_error_file_count,
        scanned_file_count=0,
        ignored_file_count=0,
        syntax_error_file_count=0,
    )
    enabled_plugin_files_json: JsonArray = [file_name for file_name in sorted(enabled_plugin_files)]
    return {
        "risk": risk,
        "enabled_plugin_files": enabled_plugin_files_json,
        "candidate_count": 0,
        "syntax_errors": [],
        "files": [],
    }


def _native_plugin_source_file_ast_map_json(
    *,
    file_name: str,
    source: str,
    active: bool,
    candidates: list[JsonObject],
) -> JsonObject:
    """构造单个插件源码文件的 AST map JSON。"""
    candidates_json: JsonArray = [candidate for candidate in candidates]
    active_candidates = [
        candidate
        for candidate in candidates
        if _json_bool(candidate, "active", f"plugin-source-ast-map.files[{file_name}].candidates[]")
    ]
    strong_count = sum(
        1
        for candidate in active_candidates
        if _json_str(candidate, "confidence", f"plugin-source-ast-map.files[{file_name}].candidates[]") == "strong"
    )
    medium_count = sum(
        1
        for candidate in active_candidates
        if _json_str(candidate, "confidence", f"plugin-source-ast-map.files[{file_name}].candidates[]") == "medium"
    )
    return {
        "file": file_name,
        "file_hash": build_plugin_source_file_hash(source),
        "active": active,
        "strong_context_text_count": strong_count,
        "medium_confidence_text_count": medium_count,
        "file_score": strong_count * 3 + medium_count,
        "candidates": candidates_json,
    }


def _native_plugin_source_candidate_to_ast_map_json(candidate: JsonObject, label: str) -> JsonObject:
    """把 Rust 插件源码候选压成当前 AST map 候选 JSON。"""
    ast_context = ensure_json_object(candidate["ast_context"], f"{label}.ast_context")
    return {
        "file": _native_plugin_source_candidate_file(candidate, label),
        "line": _json_int(candidate, "line", label),
        "selector": _json_str(candidate, "selector", label),
        "text": _json_str(candidate, "text", label),
        "context": _json_str(candidate, "context", label),
        "api": _json_str(candidate, "api", label),
        "key": _json_str(candidate, "key", label),
        "ast_context": {key: value for key, value in ast_context.items()},
        "active": _json_bool(candidate, "active", label),
        "confidence": _json_str(candidate, "confidence", label),
        "structural_flags": _json_string_array(candidate, "structural_flags", label),
    }


def _native_plugin_source_candidate_to_scan_candidate(candidate: JsonObject, label: str) -> PluginSourceCandidate:
    """把 Rust 插件源码候选转换成当前规则扫描候选对象。"""
    ast_context = ensure_json_object(candidate["ast_context"], f"{label}.ast_context")
    return PluginSourceCandidate(
        file_name=_native_plugin_source_candidate_file(candidate, label),
        selector=_json_str(candidate, "selector", label),
        text=_json_str(candidate, "text", label),
        raw_text=_json_str(candidate, "raw_text", label),
        quote=_json_str(candidate, "quote", label),
        line=_json_int(candidate, "line", label),
        start_index=_json_int(candidate, "start_index", label),
        end_index=_json_int(candidate, "end_index", label),
        content_start_index=_json_int(candidate, "content_start_index", label),
        content_end_index=_json_int(candidate, "content_end_index", label),
        context=_json_str(candidate, "context", label),
        api=_json_str(candidate, "api", label),
        key=_json_str(candidate, "key", label),
        ast_context={key: value for key, value in ast_context.items()},
        active=_json_bool(candidate, "active", label),
        confidence=_json_str(candidate, "confidence", label),
        structural_flags=tuple(str(flag) for flag in _json_string_array(candidate, "structural_flags", label)),
    )


def _native_plugin_source_syntax_error_files(syntax_errors: JsonArray) -> set[str]:
    """读取 Rust 插件源码语法错误文件名集合。"""
    file_names: set[str] = set()
    for index, raw_error in enumerate(syntax_errors):
        label = f"native_rule_candidates_result.scan_summary.plugin_source.syntax_errors[{index}]"
        error = ensure_json_object(raw_error, label)
        file_names.add(_json_str(error, "file", label))
    return file_names


def _native_plugin_source_syntax_error_map(syntax_errors: JsonArray) -> dict[str, str]:
    """读取 Rust 插件源码语法错误文件名和错误说明。"""
    errors: dict[str, str] = {}
    for index, raw_error in enumerate(syntax_errors):
        label = f"native_rule_candidates_result.scan_summary.plugin_source.syntax_errors[{index}]"
        error = ensure_json_object(raw_error, label)
        errors[_json_str(error, "file", label)] = _json_str(error, "syntax_error", label)
    return errors


def _native_plugin_source_candidate_should_translate(
    candidate: JsonObject,
    text_rules: TextRules,
    index: int,
) -> bool:
    """用 Python re 语义执行用户配置的最终源文识别。"""
    text = _json_str(candidate, "text", f"native_rule_candidates_result.candidates[{index}]")
    return text_rules.should_translate_source_text(text)


def _native_plugin_source_candidate_file(candidate: JsonObject, label: str) -> str:
    """读取 Rust 插件源码候选所属文件名。"""
    if "file" in candidate:
        return _json_str(candidate, "file", label)
    return _json_str(candidate, "source_file", label)


def _json_bool(payload: JsonObject, key: str, label: str) -> bool:
    """读取 JSON 布尔字段。"""
    value = payload.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{label}.{key} 必须是布尔值")
    return value


def _json_int(payload: JsonObject, key: str, label: str) -> int:
    """读取 JSON 整数字段。"""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label}.{key} 必须是整数")
    return value


def _json_str(payload: JsonObject, key: str, label: str) -> str:
    """读取 JSON 字符串字段。"""
    value = payload.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{label}.{key} 必须是字符串")
    return value


def _json_string_array(payload: JsonObject, key: str, label: str) -> JsonArray:
    """读取 JSON 字符串数组字段。"""
    values: JsonArray = []
    for index, item in enumerate(ensure_json_array(payload[key], f"{label}.{key}")):
        if not isinstance(item, str):
            raise TypeError(f"{label}.{key}[{index}] 必须是字符串")
        values.append(item)
    return values


def _summary_int(summary: JsonObject, key: str) -> int:
    """读取摘要整数。"""
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} 必须是整数")
    return value


__all__ = [
    "build_native_plugin_source_ast_map_payload",
    "build_native_plugin_source_ast_map_payload_and_risk_report_from_inputs",
    "build_native_plugin_source_ast_map_payload_from_inputs",
    "build_native_plugin_source_risk_report",
    "build_native_plugin_source_risk_report_from_inputs",
    "build_native_plugin_source_scan",
    "native_plugin_source_risk_report_from_ast_map",
    "native_plugin_source_risk_report_from_scan",
]
