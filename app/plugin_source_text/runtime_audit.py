"""当前运行插件源码审计。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from app.native_javascript_ast import NativeRuntimeLiteralIssueFact, collect_native_runtime_literal_issue_facts
from app.plugin_text import extract_plugin_name
from app.rmmz.schema import (
    GameData,
    PluginSourceRuntimeScanCacheRecord,
    PluginSourceRuntimeStringLiteralCacheRecord,
    PluginSourceRuntimeWriteMapRecord,
    PluginSourceTextRuleRecord,
)
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules, coerce_json_value, ensure_json_object

from .scanner import (
    PluginSourceBatchTextScan,
    PluginSourceCandidateIndex,
    PluginSourceFileTextScan,
    PluginSourceStringLiteral,
    build_plugin_source_file_hash,
    scan_plugin_source_runtime_files_text_strict,
)
from .runtime_mapping import plugin_source_runtime_hash_text

type ActiveRuntimeMappingStatus = Literal[
    "mapped_translate",
    "mapped_excluded",
    "runtime_mapping_missing",
    "runtime_mapping_stale",
    "not_applicable",
]
type ActiveRuntimeActionability = Literal[
    "fix_translation",
    "review_plugin_source_rules",
    "review_plugin_source_code",
    "fix_runtime_file",
]


@dataclass(frozen=True, slots=True)
class ActiveRuntimePluginSourceIssue:
    """当前运行插件源码中的一个审计问题。"""

    code: str
    message: str
    file_name: str
    active: bool = True
    blocking: bool = True
    fragment: str = ""
    literal: PluginSourceStringLiteral | None = None
    read_error: str = ""
    syntax_error: str = ""
    mapping_status: ActiveRuntimeMappingStatus = "not_applicable"
    actionability: ActiveRuntimeActionability = "fix_runtime_file"
    source_review_required: bool = False
    hint: JsonObject | None = None

    def to_json_object(self) -> JsonObject:
        """转换成报告 JSON 对象。"""
        if self.literal is None:
            payload: JsonObject = {
                "file": self.file_name,
                "active": self.active,
            }
        else:
            payload = self.literal.to_json_object()
        payload["code"] = self.code
        payload["message"] = self.message
        payload["blocking"] = self.blocking
        payload["fragment"] = self.fragment
        payload["mapping_status"] = self.mapping_status
        payload["actionability"] = self.actionability
        payload["source_review_required"] = self.source_review_required
        if self.read_error:
            payload["read_error"] = self.read_error
        if self.syntax_error:
            payload["syntax_error"] = self.syntax_error
        if self.hint is not None:
            payload["hint"] = self.hint
        return payload


@dataclass(frozen=True, slots=True)
class ActiveRuntimePluginSourceScanCacheStats:
    """当前运行插件源码 AST 扫描缓存统计。"""

    input_record_count: int
    current_file_count: int
    hit_file_count: int
    miss_file_count: int
    stale_file_count: int
    orphan_record_count: int
    reused_syntax_error_file_count: int
    rescan_file_count: int
    refreshed_record_count: int

    def to_summary_json(self) -> JsonObject:
        """转换成审计摘要字段。"""
        return {
            "active_runtime_scan_cache_input_record_count": self.input_record_count,
            "active_runtime_scan_cache_current_file_count": self.current_file_count,
            "active_runtime_scan_cache_hit_file_count": self.hit_file_count,
            "active_runtime_scan_cache_miss_file_count": self.miss_file_count,
            "active_runtime_scan_cache_stale_file_count": self.stale_file_count,
            "active_runtime_scan_cache_orphan_record_count": self.orphan_record_count,
            "active_runtime_scan_cache_reused_syntax_error_file_count": self.reused_syntax_error_file_count,
            "active_runtime_scan_cache_rescan_file_count": self.rescan_file_count,
            "active_runtime_scan_cache_refreshed_record_count": self.refreshed_record_count,
        }


@dataclass(frozen=True, slots=True)
class _LiteralIssueClassification:
    """运行字符串文本问题的阻断等级和可行动分类。"""

    blocking: bool
    mapping_status: ActiveRuntimeMappingStatus
    actionability: ActiveRuntimeActionability
    source_review_required: bool


@dataclass(frozen=True, slots=True)
class ActiveRuntimePluginSourceAudit:
    """当前运行插件源码审计结果。"""

    issues: tuple[ActiveRuntimePluginSourceIssue, ...]
    text_issue_audit_enabled: bool
    scanned_file_count: int
    active_file_count: int
    literal_count: int
    active_literal_count: int
    read_error_file_count: int
    scan_cache_stats: ActiveRuntimePluginSourceScanCacheStats | None = None

    @property
    def issue_counts(self) -> Counter[str]:
        """按问题编码统计数量。"""
        return Counter(issue.code for issue in self.issues)

    def summary_json(self) -> JsonObject:
        """转换成质量报告摘要字段。"""
        counts = self.issue_counts
        default_count = 0
        summary: JsonObject = {
            "active_runtime_scanned_file_count": self.scanned_file_count,
            "active_runtime_active_file_count": self.active_file_count,
            "active_runtime_literal_count": self.literal_count,
            "active_runtime_active_literal_count": self.active_literal_count,
            "active_runtime_text_issue_audit_enabled": self.text_issue_audit_enabled,
            "active_runtime_read_error_file_count": self.read_error_file_count,
            "active_runtime_issue_count": len(self.issues),
            "active_runtime_blocking_issue_count": sum(1 for issue in self.issues if issue.blocking),
            "active_runtime_warning_issue_count": sum(1 for issue in self.issues if not issue.blocking),
            "active_runtime_read_error_count": counts.get("active_runtime_read_error", default_count),
            "active_runtime_syntax_error_count": counts.get("active_runtime_syntax_error", default_count),
            "active_runtime_source_residual_count": counts.get("active_runtime_source_residual", default_count),
            "active_runtime_placeholder_risk_count": counts.get("active_runtime_placeholder_risk", default_count),
        }
        if self.scan_cache_stats is not None:
            summary.update(self.scan_cache_stats.to_summary_json())
        return summary

    def issues_json(self, *, limit: int = 100) -> JsonArray:
        """返回前 N 条审计问题。"""
        return [issue.to_json_object() for issue in self.issues[:limit]]


def audit_active_runtime_plugin_source(
    *,
    game_data: GameData,
    text_rules: TextRules,
    plugin_source_files: dict[str, str] | None = None,
    plugin_source_read_errors: dict[str, str] | None = None,
    plugin_source_batch_scan: PluginSourceBatchTextScan | None = None,
    runtime_write_map_records: list[PluginSourceRuntimeWriteMapRecord] | None = None,
    plugin_source_rule_records: list[PluginSourceTextRuleRecord] | None = None,
    scan_cache_stats: ActiveRuntimePluginSourceScanCacheStats | None = None,
    audit_text_issues: bool = True,
    text_issue_scope_keys: frozenset[tuple[str, str]] | None = None,
) -> ActiveRuntimePluginSourceAudit:
    """审计当前运行插件源码中的源文残留和坏控制符。"""
    enabled_plugin_files = _enabled_plugin_source_file_names(game_data)
    source_files = plugin_source_files if plugin_source_files is not None else game_data.plugin_source_files
    read_errors = (
        plugin_source_read_errors
        if plugin_source_read_errors is not None
        else game_data.plugin_source_read_errors
    )
    issues: list[ActiveRuntimePluginSourceIssue] = []
    runtime_write_map_by_key = {
        (record.runtime_file_name, record.runtime_selector): record
        for record in (runtime_write_map_records or [])
    }
    managed_runtime_file_names = {
        record.runtime_file_name
        for record in (runtime_write_map_records or [])
    }
    excluded_source_review_keys = _reviewed_excluded_source_keys(
        source_files=source_files,
        plugin_source_rule_records=plugin_source_rule_records or [],
    )
    literal_count = 0
    active_literal_count = 0
    active_read_error_file_names = {
        file_name
        for file_name in read_errors
        if file_name in enabled_plugin_files
    }
    active_missing_file_names = set(enabled_plugin_files) - set(source_files) - set(read_errors)
    active_file_count = len(active_read_error_file_names) + len(active_missing_file_names)
    batch_scan = plugin_source_batch_scan or scan_plugin_source_runtime_files_text_strict(
        files=source_files,
        active_file_names=enabled_plugin_files,
    )
    native_issue_facts = (
        _collect_native_literal_issue_facts_by_key(batch_scan=batch_scan, text_rules=text_rules)
        if audit_text_issues
        else {}
    )
    for file_name in sorted(active_read_error_file_names):
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_read_error",
                message="当前游戏运行文件里的插件源码读取失败，不能确认是否存在漏翻、坏控制符或 JS 语法错误",
                file_name=file_name,
                read_error=read_errors[file_name],
            )
        )
    for file_name in sorted(active_missing_file_names):
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_read_error",
                message="当前游戏运行文件里的启用插件源码文件不存在，不能确认是否存在漏翻、坏控制符或 JS 语法错误",
                file_name=file_name,
                read_error=f"启用插件源码文件不存在: js/plugins/{file_name}",
            )
        )
    for file_name, _source in sorted(source_files.items()):
        active = file_name in enabled_plugin_files
        if active:
            active_file_count += 1
            syntax_error = batch_scan.syntax_errors.get(file_name)
            if syntax_error is not None:
                issues.append(
                    _strict_active_runtime_syntax_issue(
                        file_name=file_name,
                        error=RuntimeError(syntax_error),
                        active=True,
                        blocking=file_name in managed_runtime_file_names,
                    )
                )
                continue
        else:
            syntax_error = batch_scan.syntax_errors.get(file_name)
            if syntax_error is not None:
                issues.append(
                    _strict_active_runtime_syntax_issue(
                        file_name=file_name,
                        error=RuntimeError(syntax_error),
                        active=False,
                        blocking=file_name in managed_runtime_file_names,
                    )
                )
                continue
        file_scan = batch_scan.file_scans[file_name]
        literals = file_scan.literals
        literal_count += len(literals)
        if not active:
            continue
        active_literal_count += len(literals)
        if not audit_text_issues:
            continue
        for literal in literals:
            literal_scope_key = (literal.file_name, literal.selector)
            if text_issue_scope_keys is not None and literal_scope_key not in text_issue_scope_keys:
                continue
            issues.extend(
                _audit_literal(
                    literal=literal,
                    text_rules=text_rules,
                    native_issue_fact=native_issue_facts.get(_literal_fact_key(literal)),
                    runtime_write_map_by_key=runtime_write_map_by_key,
                    excluded_source_review_keys=excluded_source_review_keys,
                )
            )
    return ActiveRuntimePluginSourceAudit(
        issues=tuple(issues),
        text_issue_audit_enabled=audit_text_issues,
        scanned_file_count=len(set(source_files) | set(read_errors) | active_missing_file_names),
        active_file_count=active_file_count,
        literal_count=literal_count,
        active_literal_count=active_literal_count,
        read_error_file_count=len(set(read_errors) | active_missing_file_names),
        scan_cache_stats=scan_cache_stats,
    )


def audit_active_runtime_plugin_source_with_scan_cache(
    *,
    game_data: GameData,
    text_rules: TextRules,
    cache_records: list[PluginSourceRuntimeScanCacheRecord],
    created_at: str,
    runtime_write_map_records: list[PluginSourceRuntimeWriteMapRecord] | None = None,
    plugin_source_rule_records: list[PluginSourceTextRuleRecord] | None = None,
    audit_text_issues: bool = True,
    text_issue_scope_keys: frozenset[tuple[str, str]] | None = None,
) -> tuple[ActiveRuntimePluginSourceAudit, list[PluginSourceRuntimeScanCacheRecord]]:
    """审计当前运行插件源码，并按文件 hash 复用 AST 扫描缓存。"""
    enabled_plugin_files = _enabled_plugin_source_file_names(game_data)
    batch_scan, refreshed_cache_records, scan_cache_stats = scan_plugin_source_files_text_strict_with_cache(
        files=game_data.plugin_source_files,
        active_file_names=enabled_plugin_files,
        cache_records=cache_records,
        created_at=created_at,
    )
    audit = audit_active_runtime_plugin_source(
        game_data=game_data,
        text_rules=text_rules,
        plugin_source_batch_scan=batch_scan,
        runtime_write_map_records=runtime_write_map_records,
        plugin_source_rule_records=plugin_source_rule_records,
        scan_cache_stats=scan_cache_stats,
        audit_text_issues=audit_text_issues,
        text_issue_scope_keys=text_issue_scope_keys,
    )
    return audit, refreshed_cache_records


def scan_plugin_source_files_text_strict_with_cache(
    *,
    files: dict[str, str],
    active_file_names: frozenset[str],
    cache_records: list[PluginSourceRuntimeScanCacheRecord],
    created_at: str,
) -> tuple[
    PluginSourceBatchTextScan,
    list[PluginSourceRuntimeScanCacheRecord],
    ActiveRuntimePluginSourceScanCacheStats,
]:
    """按文件 hash 复用当前运行插件源码 AST 扫描结果。"""
    cached_by_file = {
        record.file_name: record
        for record in cache_records
    }
    current_hashes = {
        file_name: build_plugin_source_file_hash(source)
        for file_name, source in files.items()
    }
    file_scans: dict[str, PluginSourceFileTextScan] = {}
    syntax_errors: dict[str, str] = {}
    uncached_files: dict[str, str] = {}
    hit_file_count = 0
    miss_file_count = 0
    stale_file_count = 0
    reused_syntax_error_file_count = 0
    for file_name, source in sorted(files.items()):
        file_hash = current_hashes[file_name]
        cached_record = cached_by_file.get(file_name)
        if cached_record is None:
            miss_file_count += 1
            uncached_files[file_name] = source
            continue
        if cached_record.file_hash != file_hash:
            stale_file_count += 1
            uncached_files[file_name] = source
            continue
        hit_file_count += 1
        if cached_record.syntax_error:
            reused_syntax_error_file_count += 1
            syntax_errors[file_name] = cached_record.syntax_error
            continue
        file_scans[file_name] = _file_scan_from_cache_record(
            record=cached_record,
            active=file_name in active_file_names,
        )

    if uncached_files:
        fresh_scan = scan_plugin_source_runtime_files_text_strict(
            files=uncached_files,
            active_file_names=active_file_names,
        )
        file_scans.update(fresh_scan.file_scans)
        syntax_errors.update(fresh_scan.syntax_errors)

    batch_scan = PluginSourceBatchTextScan(
        file_scans=file_scans,
        syntax_errors=syntax_errors,
    )
    refreshed_cache_records = _cache_records_from_batch_scan(
        batch_scan=batch_scan,
        current_hashes=current_hashes,
        created_at=created_at,
    )
    scan_cache_stats = ActiveRuntimePluginSourceScanCacheStats(
        input_record_count=len(cache_records),
        current_file_count=len(files),
        hit_file_count=hit_file_count,
        miss_file_count=miss_file_count,
        stale_file_count=stale_file_count,
        orphan_record_count=len(set(cached_by_file) - set(files)),
        reused_syntax_error_file_count=reused_syntax_error_file_count,
        rescan_file_count=len(uncached_files),
        refreshed_record_count=len(refreshed_cache_records),
    )
    return batch_scan, refreshed_cache_records, scan_cache_stats


def _file_scan_from_cache_record(
    *,
    record: PluginSourceRuntimeScanCacheRecord,
    active: bool,
) -> PluginSourceFileTextScan:
    """把数据库缓存记录恢复为运行期 AST 扫描对象。"""
    literals = tuple(
        PluginSourceStringLiteral(
            file_name=record.file_name,
            selector=literal.selector,
            text=literal.text,
            raw_text=literal.raw_text,
            line=literal.line,
            start_index=literal.start_index,
            end_index=literal.end_index,
            active=active,
            context=literal.context,
            literal_kind=literal.literal_kind,
            audit_default_severity=literal.audit_default_severity,
        )
        for literal in record.literals
    )
    return PluginSourceFileTextScan(
        file_name=record.file_name,
        file_hash=record.file_hash,
        literals=literals,
        candidate_index=PluginSourceCandidateIndex(candidates=(), by_selector={}),
    )


def _cache_records_from_batch_scan(
    *,
    batch_scan: PluginSourceBatchTextScan,
    current_hashes: dict[str, str],
    created_at: str,
) -> list[PluginSourceRuntimeScanCacheRecord]:
    """把运行期 AST 扫描对象转换为数据库缓存记录。"""
    records: list[PluginSourceRuntimeScanCacheRecord] = []
    for file_name in sorted(current_hashes):
        file_hash = current_hashes[file_name]
        syntax_error = batch_scan.syntax_errors.get(file_name, "")
        file_scan = batch_scan.file_scans.get(file_name)
        records.append(
            PluginSourceRuntimeScanCacheRecord(
                file_name=file_name,
                file_hash=file_hash,
                syntax_error=syntax_error,
                literals=[
                    PluginSourceRuntimeStringLiteralCacheRecord(
                        selector=literal.selector,
                        text=literal.text,
                        raw_text=literal.raw_text,
                        line=literal.line,
                        start_index=literal.start_index,
                        end_index=literal.end_index,
                        context=literal.context,
                        literal_kind=literal.literal_kind,
                        audit_default_severity=literal.audit_default_severity,
                    )
                    for literal in (file_scan.literals if file_scan is not None else ())
                ],
                created_at=created_at,
            )
        )
    return records


def _strict_active_runtime_syntax_issue(
    *,
    file_name: str,
    error: BaseException,
    active: bool,
    blocking: bool,
) -> ActiveRuntimePluginSourceIssue:
    """把严格 AST 扫描失败转换成当前运行语法问题。"""
    if blocking:
        message = "当前游戏运行文件里的插件源码无法完成 JS 语法检查，不能确认 ATT-MZ 写回的插件源码是否安全"
    else:
        message = "当前游戏运行文件里的插件源码无法完成 JS 语法检查，已跳过该文件的插件源码文本审计"
    return ActiveRuntimePluginSourceIssue(
        code="active_runtime_syntax_error",
        message=message,
        file_name=file_name,
        active=active,
        blocking=blocking,
        syntax_error=f"{type(error).__name__}: {error}",
    )


def _collect_native_literal_issue_facts_by_key(
    *,
    batch_scan: PluginSourceBatchTextScan,
    text_rules: TextRules,
) -> dict[tuple[str, str], NativeRuntimeLiteralIssueFact]:
    """按当前文本规则从 Rust 收集运行源码字符串风险事实。"""
    native_input: dict[str, tuple[str, str]] = {}
    key_by_id: dict[str, tuple[str, str]] = {}
    for file_scan in batch_scan.file_scans.values():
        for literal in file_scan.literals:
            key = _literal_fact_key(literal)
            literal_id = _literal_fact_id(key)
            native_input[literal_id] = (literal.raw_text, literal.text)
            key_by_id[literal_id] = key
    if not native_input:
        return {}
    native_facts = collect_native_runtime_literal_issue_facts(
        literals=native_input,
        text_rules=text_rules,
    )
    return {
        key_by_id[literal_id]: fact
        for literal_id, fact in native_facts.items()
    }


def _literal_fact_key(literal: PluginSourceStringLiteral) -> tuple[str, str]:
    """返回运行源码字符串风险事实的稳定键。"""
    return (literal.file_name, literal.selector)


def _literal_fact_id(key: tuple[str, str]) -> str:
    """把稳定键编码为 native batch 内部 ID。"""
    file_name, selector = key
    return f"{file_name}\n{selector}"


def _control_hint_for_fragment(
    native_issue_fact: NativeRuntimeLiteralIssueFact | None,
    fragment: str,
) -> JsonObject | None:
    """按 fragment 取 Rust 控制符拆分 hint。"""
    if native_issue_fact is None:
        return None
    for raw_hint in native_issue_fact.control_code_hints:
        hint = ensure_json_object(coerce_json_value(raw_hint), "runtime_literal.control_code_hint")
        original = hint.get("original")
        if original != fragment:
            continue
        return hint
    return None


def _audit_literal(
    *,
    literal: PluginSourceStringLiteral,
    text_rules: TextRules,
    native_issue_fact: NativeRuntimeLiteralIssueFact | None,
    runtime_write_map_by_key: dict[tuple[str, str], PluginSourceRuntimeWriteMapRecord],
    excluded_source_review_keys: frozenset[tuple[str, str]],
) -> list[ActiveRuntimePluginSourceIssue]:
    """审计单个当前运行字符串字面量。"""
    classification = _classify_literal_issue(
        literal=literal,
        text_rules=text_rules,
        runtime_write_map_by_key=runtime_write_map_by_key,
        excluded_source_review_keys=excluded_source_review_keys,
    )
    if classification.mapping_status == "mapped_excluded":
        return []
    issues: list[ActiveRuntimePluginSourceIssue] = []
    placeholder_fragments = () if native_issue_fact is None else native_issue_fact.placeholder_fragments
    for fragment in placeholder_fragments:
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_placeholder_risk",
                message="当前游戏运行文件里的插件源码存在未受保护的游戏控制符片段",
                file_name=literal.file_name,
                fragment=fragment,
                literal=literal,
                blocking=classification.blocking,
                mapping_status=classification.mapping_status,
                actionability=classification.actionability,
                source_review_required=classification.source_review_required,
                hint=_control_hint_for_fragment(native_issue_fact, fragment),
            )
        )
    try:
        text_rules.check_source_residual([literal.text])
    except ValueError as error:
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_source_residual",
                message=f"当前游戏运行文件里的插件源码仍有源文残留: {error}",
                file_name=literal.file_name,
                fragment="",
                literal=literal,
                blocking=classification.blocking,
                mapping_status=classification.mapping_status,
                actionability=classification.actionability,
                source_review_required=classification.source_review_required,
            )
        )
    return _deduplicate_issues(issues)


def _classify_literal_issue(
    *,
    literal: PluginSourceStringLiteral,
    text_rules: TextRules,
    runtime_write_map_by_key: dict[tuple[str, str], PluginSourceRuntimeWriteMapRecord],
    excluded_source_review_keys: frozenset[tuple[str, str]],
) -> _LiteralIssueClassification:
    """按映射和源规则审查状态计算文本问题是否阻断。"""
    record = runtime_write_map_by_key.get((literal.file_name, literal.selector))
    if record is not None:
        if record.runtime_text_hash == plugin_source_runtime_hash_text(literal.text):
            if record.mapping_kind == "excluded":
                return _LiteralIssueClassification(
                    blocking=False,
                    mapping_status="mapped_excluded",
                    actionability="review_plugin_source_code",
                    source_review_required=False,
                )
            return _LiteralIssueClassification(
                blocking=True,
                mapping_status="mapped_translate",
                actionability="fix_translation",
                source_review_required=False,
            )
        return _LiteralIssueClassification(
            blocking=True,
            mapping_status="runtime_mapping_stale",
            actionability="fix_runtime_file",
            source_review_required=False,
        )

    if (literal.file_name, literal.selector) in excluded_source_review_keys:
        return _LiteralIssueClassification(
            blocking=False,
            mapping_status="runtime_mapping_missing",
            actionability="review_plugin_source_code",
            source_review_required=False,
        )

    if literal.audit_default_severity == "blocking":
        return _LiteralIssueClassification(
            blocking=True,
            mapping_status="runtime_mapping_missing",
            actionability="review_plugin_source_rules",
            source_review_required=True,
        )

    if literal.audit_default_severity == "ignore":
        return _LiteralIssueClassification(
            blocking=False,
            mapping_status="runtime_mapping_missing",
            actionability="review_plugin_source_code",
            source_review_required=False,
        )

    source_review_required = (
        literal.literal_kind == "unknown"
        and text_rules.should_translate_source_text(literal.text)
    )
    return _LiteralIssueClassification(
        blocking=source_review_required,
        mapping_status="runtime_mapping_missing",
        actionability="review_plugin_source_rules" if source_review_required else "review_plugin_source_code",
        source_review_required=source_review_required,
    )


def _reviewed_excluded_source_keys(
    *,
    source_files: dict[str, str],
    plugin_source_rule_records: list[PluginSourceTextRuleRecord],
) -> frozenset[tuple[str, str]]:
    """返回当前源码 hash 下已人工排除的 selector。"""
    keys: set[tuple[str, str]] = set()
    for record in plugin_source_rule_records:
        source = source_files.get(record.file_name)
        if source is None:
            continue
        if build_plugin_source_file_hash(source) != record.file_hash:
            continue
        for selector in record.excluded_selectors:
            keys.add((record.file_name, selector))
    return frozenset(keys)


def _deduplicate_issues(
    issues: list[ActiveRuntimePluginSourceIssue],
) -> list[ActiveRuntimePluginSourceIssue]:
    """去掉同一字面量内重复报告的问题。"""
    seen: set[tuple[str, str, str, str, str, str]] = set()
    deduplicated: list[ActiveRuntimePluginSourceIssue] = []
    for issue in issues:
        selector = issue.literal.selector if issue.literal is not None else ""
        key = (issue.code, issue.file_name, selector, issue.fragment, issue.read_error, issue.syntax_error)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(issue)
    return deduplicated


def _enabled_plugin_source_file_names(game_data: GameData) -> frozenset[str]:
    """从当前插件配置读取实际启用的直接插件源码文件名。"""
    file_names: set[str] = set()
    for plugin_index, plugin in enumerate(game_data.plugins_js):
        if plugin.get("status") is not True:
            continue
        plugin_name = extract_plugin_name(plugin, plugin_index).strip()
        if plugin_name:
            file_names.add(f"{plugin_name}.js")
    return frozenset(file_names)


__all__ = [
    "ActiveRuntimePluginSourceAudit",
    "ActiveRuntimePluginSourceIssue",
    "ActiveRuntimePluginSourceScanCacheStats",
    "audit_active_runtime_plugin_source",
    "audit_active_runtime_plugin_source_with_scan_cache",
    "scan_plugin_source_files_text_strict_with_cache",
]
