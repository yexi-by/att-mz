"""翻译与写入前置硬闸。

本模块把 Skill 中“必须先完成”的步骤固化为程序不变量。翻译、质量报告和写入游戏文件
都应复用这里的检查，避免不同入口各写一套宽松判断。
"""

from __future__ import annotations

import json
from app.application.errors import WorkflowGateError
from app.config.schemas import Setting, TextRulesSetting
from app.event_command_text import resolve_event_command_codes
from app.native_placeholder_scan import (
    collect_native_placeholder_candidate_details,
    count_uncovered_placeholder_candidate_details,
)
from app.native_structured_placeholder_scan import (
    collect_native_structured_placeholder_candidate_details,
    count_uncovered_structured_placeholder_candidate_details,
)
from app.nonstandard_data import (
    StaleNonstandardDataRulesError,
    nonstandard_data_rule_records_to_import_file,
    validate_nonstandard_data_rules,
)
from app.nonstandard_data.scanner import build_nonstandard_data_scan
from app.persistence import TargetGameSession
from app.plugin_text import collect_plugin_json_string_leaf_candidates, extract_plugin_name
from app.plugin_source_text import (
    PluginSourceScan,
    build_native_plugin_source_scan,
    filter_fresh_plugin_source_text_rules,
)
from app.rmmz.commands import iter_all_commands
from app.rmmz.control_codes import StructuredPlaceholderRule
from app.rmmz.game_file_view import GameFileView
from app.rmmz.mv_namebox_native import scan_native_mv_virtual_namebox
from app.rmmz.schema import GameData, TranslationData, TranslationItem
from app.rmmz.text_rules import JsonArray, JsonObject, JsonValue, TextRules
from app.rule_review_decision import (
    RuleCoverageResult,
    RuleReviewDecision as CandidateReviewDecision,
    RuleReviewSeverity as CandidateReviewSeverity,
    RuleReviewStage as CandidateReviewStage,
    WorkflowGateIssue,
    build_empty_rule_review_decision,
    build_rule_review_decision,
)
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    RuleReviewDomain,
    event_command_rule_scope_hash_for_codes,
    placeholder_rule_scope_hash,
    plugin_rule_scope_hash,
    structured_placeholder_rule_scope_hash,
)
from app.terminology import collect_terminology_bundle_errors
from app.text_index import read_current_text_index_gate_facts, text_index_gate_facts_to_workflow_gate_issues
from app.text_scope import TextScopeResult, read_fresh_plugin_text_rules


def collect_native_note_tag_candidate_details(*, game_data: GameData, text_rules: TextRules) -> JsonArray:
    """延迟导入 native Note 标签候选扫描，避免 Note 标签包初始化循环。"""
    from app.native_note_tag_scan import collect_native_note_tag_candidate_details as collect_native

    return collect_native(game_data=game_data, text_rules=text_rules)


def collect_native_note_tag_rule_validation(
    *,
    game_data: GameData,
    text_rules: TextRules,
) -> JsonObject:
    """延迟导入 native Note 标签规则验证，避免 Note 标签包初始化循环。"""
    from app.native_note_tag_scan import collect_native_note_tag_rule_validation as collect_native

    return collect_native(game_data=game_data, text_rules=text_rules, rule_records=[])


async def collect_workflow_gate_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
    custom_placeholder_rules_supplied: bool,
    translated_items: list[TranslationItem] | None = None,
    scope: TextScopeResult | None = None,
    plugin_source_scan: PluginSourceScan | None = None,
    plugin_source_rule_gate_errors: list[WorkflowGateIssue] | None = None,
    nonstandard_data_rule_gate_errors: list[WorkflowGateIssue] | None = None,
    external_rule_gate_errors: list[WorkflowGateIssue] | None = None,
) -> list[WorkflowGateIssue]:
    """收集当前游戏不能继续翻译或写入的全部硬闸错误。"""
    if scope is None:
        _ = translated_items
        raise RuntimeError("collect_workflow_gate_errors 缺少当前文本范围，不能继续；请重新生成当前文本索引，并从当前入口传入文本范围")
    errors: list[WorkflowGateIssue] = []
    if plugin_source_rule_gate_errors is None:
        errors.extend(
            await _plugin_source_rule_gate_errors(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                scan=plugin_source_scan,
            )
        )
    else:
        errors.extend(plugin_source_rule_gate_errors)
    if nonstandard_data_rule_gate_errors is None:
        errors.extend(
            await _nonstandard_data_rule_gate_errors(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
            )
        )
    else:
        errors.extend(nonstandard_data_rule_gate_errors)
    errors.extend(await _terminology_gate_errors(session))
    if external_rule_gate_errors is None:
        errors.extend(
            await _external_rule_gate_errors(
                session=session,
                game_data=game_data,
                setting=setting,
                text_rules=text_rules,
            )
        )
    else:
        errors.extend(external_rule_gate_errors)
    placeholder_decisions = await collect_placeholder_candidate_review_decisions(
        session=session,
        scope=scope,
        text_rules=text_rules,
        custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
        stage="workflow_gate",
    )
    errors.extend(
        decision.to_issue()
        for decision in placeholder_decisions
        if decision.severity == "error"
    )
    errors.extend(_text_scope_gate_errors(scope=scope, text_rules=text_rules))
    _ = setting
    return errors


async def collect_indexed_workflow_gate_errors(
    *,
    session: TargetGameSession,
    text_rules: TextRules,
    custom_placeholder_rules_supplied: bool,
    scope: TextScopeResult | None,
    external_rule_gate_errors: list[WorkflowGateIssue],
    placeholder_gate_errors: list[WorkflowGateIssue] | None = None,
    text_scope_gate_errors: list[WorkflowGateIssue] | None = None,
) -> list[WorkflowGateIssue]:
    """收集已由索引预检覆盖 GameData 支线后的 workflow gate 错误。"""
    errors: list[WorkflowGateIssue] = []
    try:
        gate_facts = await read_current_text_index_gate_facts(session)
    except RuntimeError as error:
        errors.append(
            WorkflowGateIssue(
                code="text_index_workflow_gate_metadata_missing",
                message=str(error),
            )
        )
    else:
        errors.extend(text_index_gate_facts_to_workflow_gate_issues(gate_facts))
    errors.extend(await _terminology_gate_errors(session))
    errors.extend(external_rule_gate_errors)
    if placeholder_gate_errors is None:
        if scope is None:
            raise ValueError("缺少完整文本范围时必须传入占位符 gate 结果")
        placeholder_decisions = await collect_placeholder_candidate_review_decisions(
            session=session,
            scope=scope,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
            stage="workflow_gate",
        )
        errors.extend(
            decision.to_issue()
            for decision in placeholder_decisions
            if decision.severity == "error"
        )
    else:
        errors.extend(placeholder_gate_errors)
    if text_scope_gate_errors is None:
        if scope is None:
            raise ValueError("缺少完整文本范围时必须传入 text-scope gate 结果")
        errors.extend(_text_scope_gate_errors(scope=scope, text_rules=text_rules))
    else:
        errors.extend(text_scope_gate_errors)
    return errors


async def collect_plugin_source_workflow_gate_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    text_rules: TextRules,
    plugin_source_scan: PluginSourceScan | None = None,
) -> list[WorkflowGateIssue]:
    """收集插件源码高风险支线的同源门禁错误。"""
    return await _plugin_source_rule_gate_errors(
        session=session,
        game_data=game_data,
        text_rules=text_rules,
        scan=plugin_source_scan,
    )


async def collect_nonstandard_data_workflow_gate_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    text_rules: TextRules,
) -> list[WorkflowGateIssue]:
    """收集非标准 data 高风险支线的同源门禁错误。"""
    return await _nonstandard_data_rule_gate_errors(
        session=session,
        game_data=game_data,
        text_rules=text_rules,
    )


async def collect_external_text_rule_gate_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
) -> list[WorkflowGateIssue]:
    """收集三类外部文本规则未完成导致的前置错误。"""
    return await _external_rule_gate_errors(
        session=session,
        game_data=game_data,
        setting=setting,
        text_rules=text_rules,
    )


def format_workflow_gate_error(errors: list[WorkflowGateIssue]) -> str:
    """把硬闸错误转换成用户可读的失败原因。"""
    messages = "；".join(error.message for error in errors)
    return f"检查没通过，不能继续：{messages}"


async def assert_workflow_gate_passed(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
    custom_placeholder_rules_supplied: bool,
    translated_items: list[TranslationItem] | None = None,
    scope: TextScopeResult | None = None,
    plugin_source_scan: PluginSourceScan | None = None,
) -> None:
    """不满足流程前置条件时立刻中断当前任务。"""
    errors = await collect_workflow_gate_errors(
        session=session,
        game_data=game_data,
        setting=setting,
        text_rules=text_rules,
        custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
        translated_items=translated_items,
        scope=scope,
        plugin_source_scan=plugin_source_scan,
    )
    if errors:
        raise WorkflowGateError(format_workflow_gate_error(errors))


def ensure_empty_rule_import_allowed(
    *,
    rule_label: str,
    confirm_empty: bool,
) -> None:
    """校验空规则导入是否经过显式确认。"""
    ensure_empty_rule_confirmed(rule_label=rule_label, confirm_empty=confirm_empty)


def ensure_empty_rule_confirmed(
    *,
    rule_label: str,
    confirm_empty: bool,
) -> None:
    """校验人工审查为空的规则导入是否经过显式确认。"""
    if not confirm_empty:
        raise RuntimeError(f"{rule_label}为空，必须先确认当前游戏确实没有对应规则，再传 --confirm-empty")


def count_plugin_rule_candidates(game_data: GameData) -> int:
    """统计当前插件配置中的字符串叶子候选数量。"""
    count = 0
    for plugin_index, plugin in enumerate(game_data.plugins_js):
        plugin_name = extract_plugin_name(plugin, plugin_index)
        count += len(
            collect_plugin_json_string_leaf_candidates(
                plugin_index=plugin_index,
                plugin_name=plugin_name,
                plugin=plugin,
            )
        )
    return count


def count_event_command_rule_candidates(*, game_data: GameData, setting: Setting) -> int:
    """统计当前配置会导出的事件指令参数候选数量。"""
    command_codes = event_command_rule_codes_for_setting(game_data=game_data, setting=setting)
    return count_event_command_rule_candidates_for_codes(game_data=game_data, command_codes=command_codes)


def count_event_command_rule_candidates_for_codes(
    *,
    game_data: GameData,
    command_codes: frozenset[int],
) -> int:
    """按指定事件指令编码统计参数候选数量。"""
    if not command_codes:
        raise ValueError("事件指令编码不能为空")
    seen_samples: set[tuple[int, str]] = set()
    for _path, _display_name, command in iter_all_commands(game_data):
        if command.code not in command_codes:
            continue
        sample_key = json.dumps(command.parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        seen_samples.add((command.code, sample_key))
    return len(seen_samples)


def event_command_rule_scope_hash_for_setting(*, game_data: GameData, setting: Setting) -> str:
    """按当前事件指令导出配置计算空规则确认范围哈希。"""
    command_codes = event_command_rule_codes_for_setting(game_data=game_data, setting=setting)
    return event_command_rule_scope_hash_for_command_codes(game_data=game_data, command_codes=command_codes)


def event_command_rule_codes_for_setting(*, game_data: GameData, setting: Setting) -> frozenset[int]:
    """读取当前配置实际启用的事件指令编码集合。"""
    return resolve_event_command_codes(
        command_codes=None,
        configured_command_codes=setting.event_command_text.default_codes_for_engine(game_data.layout.engine_kind),
    )


def event_command_rule_scope_hash_for_command_codes(
    *,
    game_data: GameData,
    command_codes: frozenset[int],
) -> str:
    """按指定事件指令编码计算空规则确认范围哈希。"""
    if not command_codes:
        raise ValueError("事件指令编码不能为空")
    return event_command_rule_scope_hash_for_codes(game_data=game_data, command_codes=command_codes)


def count_note_tag_rule_candidates(*, game_data: GameData, text_rules: TextRules) -> int:
    """统计当前 Note 标签候选中实际含可翻译值的数量。"""
    candidates = collect_native_note_tag_candidate_details(game_data=game_data, text_rules=text_rules)
    return _candidate_int_sum(candidates, "translatable_hit_count")


def note_tag_rule_scope_hash_for_text_rules(*, game_data: GameData, text_rules: TextRules) -> str:
    """按当前文本规则计算 Note 标签空规则确认范围哈希。"""
    validation = collect_native_note_tag_rule_validation(game_data=game_data, text_rules=text_rules)
    scope_hash = validation.get("scope_hash")
    if not isinstance(scope_hash, str) or not scope_hash:
        raise RuntimeError("native Note 标签规则验证缺少 scope_hash，请重新构建 Rust 原生扩展")
    return scope_hash


def mv_virtual_namebox_rule_scope_hash_for_game_data(game_data: GameData) -> str:
    """按 native MV 虚拟名字框候选计算空规则确认范围哈希。"""
    native_scan = scan_native_mv_virtual_namebox(game_data=game_data)
    return native_scan.scope_hash


def normal_placeholder_scope_hash(
    *,
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
) -> str:
    """计算普通占位符空规则确认依赖的当前候选哈希。"""
    coverage = build_normal_placeholder_coverage_result(
        translation_data_map=translation_data_map,
        text_rules=text_rules,
        rule_count=len(text_rules.custom_placeholder_rules),
    )
    return coverage.scope_hash


def structured_placeholder_scope_hash(
    *,
    translation_data_map: dict[str, TranslationData],
    structured_rules: tuple[StructuredPlaceholderRule, ...],
    text_rules: TextRules | None = None,
) -> str:
    """计算结构化占位符空规则确认依赖的当前候选哈希。"""
    coverage = build_structured_placeholder_coverage_result(
        translation_data_map=translation_data_map,
        structured_rules=structured_rules,
        rule_count=len(structured_rules),
        text_rules=text_rules,
    )
    return coverage.scope_hash


def build_normal_placeholder_coverage_result(
    *,
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
    rule_count: int,
) -> RuleCoverageResult:
    """构建普通占位符候选覆盖的完整内部结果。"""
    candidate_details = collect_native_placeholder_candidate_details(
        translation_data_map=translation_data_map,
        text_rules=text_rules,
    )
    uncovered_count = count_uncovered_placeholder_candidate_details(candidate_details)
    return RuleCoverageResult(
        rule_domain=PLACEHOLDER_RULE_DOMAIN,
        scope_hash=placeholder_rule_scope_hash(candidate_details),
        rule_count=rule_count,
        candidate_count=len(candidate_details),
        covered_count=len(candidate_details) - uncovered_count,
        uncovered_count=uncovered_count,
        candidates=candidate_details,
    )


def build_structured_placeholder_coverage_result(
    *,
    translation_data_map: dict[str, TranslationData],
    structured_rules: tuple[StructuredPlaceholderRule, ...],
    rule_count: int,
    text_rules: TextRules | None = None,
) -> RuleCoverageResult:
    """构建结构化占位符候选覆盖的完整内部结果。"""
    active_text_rules = (
        text_rules
        if text_rules is not None
        else _structured_placeholder_candidate_text_rules(structured_rules)
    )
    details = collect_native_structured_placeholder_candidate_details(
        translation_data_map=translation_data_map,
        text_rules=active_text_rules,
    )
    uncovered_count = count_uncovered_structured_placeholder_candidate_details(details)
    return RuleCoverageResult(
        rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
        scope_hash=structured_placeholder_rule_scope_hash(details),
        rule_count=rule_count,
        candidate_count=len(details),
        covered_count=len(details) - uncovered_count,
        uncovered_count=uncovered_count,
        candidates=details,
    )


def count_uncovered_structured_placeholder_candidates(
    *,
    translation_data_map: dict[str, TranslationData],
    structured_rules: tuple[StructuredPlaceholderRule, ...],
    text_rules: TextRules | None = None,
) -> int:
    """统计未被结构化规则覆盖的协议外壳候选数量。"""
    active_text_rules = (
        text_rules
        if text_rules is not None
        else _structured_placeholder_candidate_text_rules(structured_rules)
    )
    details = collect_native_structured_placeholder_candidate_details(
        translation_data_map=translation_data_map,
        text_rules=active_text_rules,
    )
    return count_uncovered_structured_placeholder_candidate_details(details)


def _structured_placeholder_candidate_text_rules(
    structured_rules: tuple[StructuredPlaceholderRule, ...],
) -> TextRules:
    """构造结构化候选扫描所需的最小文本规则上下文。"""
    return TextRules.from_setting(
        TextRulesSetting(),
        structured_placeholder_rules=structured_rules,
    )


async def _terminology_gate_errors(session: TargetGameSession) -> list[WorkflowGateIssue]:
    """检查字段译名表和正文术语表是否完整一致。"""
    registry = await session.read_terminology_registry()
    glossary = await session.read_terminology_glossary()
    return [
        WorkflowGateIssue(code="terminology_bundle", message=message)
        for message in collect_terminology_bundle_errors(registry=registry, glossary=glossary)
    ]


async def _external_rule_gate_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
) -> list[WorkflowGateIssue]:
    """检查插件、事件指令和 Note 标签外部规则是否完成导入或空结果确认。"""
    errors: list[WorkflowGateIssue] = []
    plugin_rules, stale_plugin_rules = await read_fresh_plugin_text_rules(
        session=session,
        game_data=game_data,
    )
    if stale_plugin_rules:
        errors.append(
            WorkflowGateIssue(
                code="stale_plugin_rules",
                message=f"存在 {len(stale_plugin_rules)} 个过期插件规则，请重新导入插件规则",
            )
        )
    if not plugin_rules and not stale_plugin_rules:
        errors.extend(
            await _empty_rule_review_errors(
                session=session,
                rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
                current_scope_hash=plugin_rule_scope_hash(game_data),
                label="插件规则",
            )
        )

    if game_data.layout.engine_kind == "mv":
        mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
        if not mv_virtual_namebox_rules:
            errors.extend(
                await _empty_rule_review_errors(
                    session=session,
                    rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
                    current_scope_hash=mv_virtual_namebox_rule_scope_hash_for_game_data(game_data),
                    label="MV 虚拟名字框规则",
                )
            )

    event_rules = await session.read_event_command_text_rules()
    if not event_rules:
        errors.extend(
            await _empty_rule_review_errors(
                session=session,
                rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
                current_scope_hash=event_command_rule_scope_hash_for_setting(
                    game_data=game_data,
                    setting=setting,
                ),
                label="事件指令规则",
            )
        )

    note_rules = await session.read_note_tag_text_rules()
    if not note_rules:
        errors.extend(
            await _empty_rule_review_errors(
                session=session,
                rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
                current_scope_hash=note_tag_rule_scope_hash_for_text_rules(
                    game_data=game_data,
                    text_rules=text_rules,
                ),
                label="Note 标签规则",
            )
        )
    return errors


async def _plugin_source_rule_gate_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    text_rules: TextRules,
    scan: PluginSourceScan | None = None,
) -> list[WorkflowGateIssue]:
    """高风险插件源码文本必须先确认并导入源码规则。"""
    records = await session.read_plugin_source_text_rules()
    if scan is None or records:
        scan = build_native_plugin_source_scan(
            game_data=game_data,
            text_rules=text_rules,
            rule_records=records,
        )
    fresh_records, stale_records = filter_fresh_plugin_source_text_rules(
        game_data=game_data,
        rule_records=records,
        text_rules=text_rules,
        scan=scan,
    )
    if stale_records:
        return [
            WorkflowGateIssue(
                code="stale_plugin_source_rules",
                message=f"存在 {len(stale_records)} 个过期插件源码规则，请重新导入插件源码规则",
            )
        ]
    if not scan.risk.high_risk and not fresh_records:
        return []
    if scan.risk.high_risk and not fresh_records:
        return [
            WorkflowGateIssue(
                code="plugin_source_text_high_risk",
                message=(
                    "发现高风险插件源码文本候选，可能有玩家可见正文存放在 js/plugins 源码文件中；"
                    "正文翻译已暂停，请先确认并完成插件源码 AST 分析支线，导入插件源码规则后再继续"
                ),
            )
        ]
    review_summary = scan.review_summary
    if review_summary is None:
        raise RuntimeError("插件源码 native scan 缺少 Rust review_summary，请重新构建原生扩展")
    if review_summary.unreviewed_selector_count == 0:
        return []
    return [
        WorkflowGateIssue(
            code="plugin_source_review_incomplete",
            message=(
                f"插件源码支线还有 {review_summary.unreviewed_selector_count} 个候选未由外部 Agent 归入翻译或排除；"
                "请补全插件源码规则后再继续"
            ),
        )
    ]


async def _nonstandard_data_rule_gate_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    text_rules: TextRules,
) -> list[WorkflowGateIssue]:
    """高风险非标准 data 文件文本必须先全量归类并导入规则。"""
    records = await session.read_nonstandard_data_text_rules()
    try:
        scan = await build_nonstandard_data_scan(
            layout=game_data.layout,
            source_view=GameFileView.TRANSLATION_SOURCE,
            text_rules=text_rules,
        )
    except Exception as error:
        return [
            WorkflowGateIssue(
                code="nonstandard_data_scan_failed",
                message=f"非标准 data 文件文本扫描失败，请先修复 data 文件后再继续: {type(error).__name__}: {error}",
            )
        ]

    if not scan.high_risk and not records:
        return []

    if scan.high_risk and not records:
        return [
            WorkflowGateIssue(
                code="nonstandard_data_high_risk",
                message=(
                    "发现非标准 data 文件里存在疑似源语言自然文本；"
                    "正文翻译已暂停，请先导出候选并导入非标准 data 文件文本规则，或按文件确认跳过"
                ),
            )
        ]

    try:
        import_file = nonstandard_data_rule_records_to_import_file(records)
        validation = validate_nonstandard_data_rules(
            scan=scan,
            import_file=import_file,
            rule_records=records,
        )
    except StaleNonstandardDataRulesError as error:
        return [
            WorkflowGateIssue(
                code="stale_nonstandard_data_rules",
                message=f"存在过期非标准 data 文件文本规则，请重新导出并导入规则: {error}",
            )
        ]
    except Exception as error:
        return [
            WorkflowGateIssue(
                code="nonstandard_data_review_incomplete",
                message=f"非标准 data 文件文本规则未覆盖当前候选，请重新导出并导入规则: {error}",
            )
        ]
    if not validation.unreviewed_candidate_paths:
        return []
    return [
        WorkflowGateIssue(
            code="nonstandard_data_review_incomplete",
            message=f"非标准 data 文件文本支线还有 {len(validation.unreviewed_candidate_paths)} 个候选未归类，请补全规则后再继续",
        )
    ]


async def collect_placeholder_candidate_review_decisions(
    *,
    session: TargetGameSession,
    scope: TextScopeResult,
    text_rules: TextRules,
    custom_placeholder_rules_supplied: bool,
    stage: CandidateReviewStage,
) -> list[CandidateReviewDecision]:
    """收集普通/结构化占位符候选在指定阶段的统一审查决策。"""
    placeholder_rule_count = len(await session.read_placeholder_rules())
    placeholder_coverage = build_normal_placeholder_coverage_result(
        translation_data_map=scope.translation_data_map,
        text_rules=text_rules,
        rule_count=placeholder_rule_count,
    )
    placeholder_decision = await _build_candidate_review_decision(
        session=session,
        coverage=placeholder_coverage,
        stage=stage,
        custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
    )
    structured_rule_count = len(await session.read_structured_placeholder_rules())
    structured_coverage = build_structured_placeholder_coverage_result(
        translation_data_map=scope.translation_data_map,
        structured_rules=text_rules.structured_placeholder_rules,
        rule_count=structured_rule_count,
        text_rules=text_rules,
    )
    structured_decision = await _build_candidate_review_decision(
        session=session,
        coverage=structured_coverage,
        stage=stage,
        custom_placeholder_rules_supplied=False,
    )
    return [placeholder_decision, structured_decision]


async def collect_placeholder_candidate_review_warnings(
    *,
    session: TargetGameSession,
    scope: TextScopeResult,
    text_rules: TextRules,
    custom_placeholder_rules_supplied: bool,
    stage: CandidateReviewStage = "quality_report",
) -> list[WorkflowGateIssue]:
    """收集已审查但仍有未覆盖占位符候选的提示。"""
    decisions = await collect_placeholder_candidate_review_decisions(
        session=session,
        scope=scope,
        text_rules=text_rules,
        custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
        stage=stage,
    )
    return [
        decision.to_issue()
        for decision in decisions
        if decision.severity == "warning"
    ]


async def _build_candidate_review_decision(
    *,
    session: TargetGameSession,
    coverage: RuleCoverageResult,
    stage: CandidateReviewStage,
    custom_placeholder_rules_supplied: bool,
) -> CandidateReviewDecision:
    """按统一阶段契约生成单个候选域的审查决策。"""
    if coverage.rule_domain == PLACEHOLDER_RULE_DOMAIN:
        unreviewed_code = "placeholder_uncovered"
        reviewed_code = "placeholder_uncovered_reviewed"
        unreviewed_message = (
            f"发现 {coverage.uncovered_count} 个未覆盖的疑似自定义控制符，"
            "请先导入普通占位符规则或确认当前候选风险"
        )
        reviewed_message = (
            f"仍有 {coverage.uncovered_count} 个未覆盖的疑似自定义控制符；"
            "当前候选已通过导入命令确认风险"
        )
    elif coverage.rule_domain == STRUCTURED_PLACEHOLDER_RULE_DOMAIN:
        unreviewed_code = "structured_placeholder_uncovered"
        reviewed_code = "structured_placeholder_uncovered_reviewed"
        unreviewed_message = (
            f"发现 {coverage.uncovered_count} 个未被结构化规则覆盖的协议外壳候选，"
            "请先导入结构化占位符规则或确认当前候选风险"
        )
        reviewed_message = (
            f"仍有 {coverage.uncovered_count} 个未被结构化规则覆盖的协议外壳候选；"
            "当前候选已通过导入命令确认风险"
        )
    else:
        raise ValueError(f"不支持的候选审查域: {coverage.rule_domain}")

    return await build_rule_review_decision(
        session=session,
        coverage=coverage,
        stage=stage,
        unreviewed_code=unreviewed_code,
        unreviewed_message=unreviewed_message,
        reviewed_code=reviewed_code,
        reviewed_message=reviewed_message,
        custom_rules_supplied=custom_placeholder_rules_supplied,
    )


def _text_scope_gate_errors(*, scope: TextScopeResult, text_rules: TextRules) -> list[WorkflowGateIssue]:
    """检查当前文本范围是否存在过期规则或不可写条目。"""
    errors: list[WorkflowGateIssue] = []
    if scope.stale_plugin_rules:
        errors.append(
            WorkflowGateIssue(
                code="stale_plugin_rules",
                message=f"存在 {len(scope.stale_plugin_rules)} 个过期插件规则，请重新导入插件规则",
            )
        )
    if scope.write_back_probe_error:
        errors.append(WorkflowGateIssue(code="write_back_probe_error", message=scope.write_back_probe_error))
    if scope.unwritable_entries:
        errors.append(
            WorkflowGateIssue(
                code="coverage_unwritable",
                message=f"存在 {len(scope.unwritable_entries)} 条当前文本无法写进游戏文件，请先运行 audit-coverage 查看明细",
            )
        )
    unwritable_rule_hit_count = sum(
        1
        for entry in scope.entries
        if not entry.enters_translation
        and entry.source_type != "standard_data"
        and text_rules.should_translate_source_lines(entry.original_lines)
    )
    if unwritable_rule_hit_count:
        errors.append(
            WorkflowGateIssue(
                code="rule_hits_unwritable",
                message=f"存在 {unwritable_rule_hit_count} 条规则命中文本没有进入当前可写范围，请先运行 audit-coverage 查看明细",
            )
        )
    return errors


async def _empty_rule_review_errors(
    *,
    session: TargetGameSession,
    rule_domain: RuleReviewDomain,
    current_scope_hash: str,
    label: str,
) -> list[WorkflowGateIssue]:
    """检查空规则是否经过显式确认且确认范围仍然有效。"""
    decision = await build_empty_rule_review_decision(
        session=session,
        rule_domain=rule_domain,
        stage="workflow_gate",
        scope_hash=current_scope_hash,
        label=label,
        missing_code=f"{rule_domain}_missing",
        stale_code=f"{rule_domain}_stale_empty_confirmation",
        missing_severity="error",
        stale_severity="error",
    )
    return [decision.to_issue()] if decision.severity == "error" else []


def _candidate_int_sum(candidates: JsonArray, key: str) -> int:
    """统计候选对象中的整数计数字段。"""
    total = 0
    for candidate_value in candidates:
        if not isinstance(candidate_value, dict):
            continue
        raw_count: JsonValue | None = candidate_value.get(key)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            continue
        total += raw_count
    return total


__all__: list[str] = [
    "CandidateReviewDecision",
    "CandidateReviewSeverity",
    "CandidateReviewStage",
    "WorkflowGateIssue",
    "collect_external_text_rule_gate_errors",
    "collect_indexed_workflow_gate_errors",
    "build_normal_placeholder_coverage_result",
    "build_structured_placeholder_coverage_result",
    "collect_placeholder_candidate_review_decisions",
    "collect_placeholder_candidate_review_warnings",
    "assert_workflow_gate_passed",
    "collect_workflow_gate_errors",
    "count_event_command_rule_candidates_for_codes",
    "event_command_rule_scope_hash_for_setting",
    "event_command_rule_codes_for_setting",
    "event_command_rule_scope_hash_for_command_codes",
    "count_event_command_rule_candidates",
    "count_note_tag_rule_candidates",
    "count_plugin_rule_candidates",
    "count_uncovered_structured_placeholder_candidates",
    "ensure_empty_rule_confirmed",
    "ensure_empty_rule_import_allowed",
    "format_workflow_gate_error",
    "mv_virtual_namebox_rule_scope_hash_for_game_data",
    "note_tag_rule_scope_hash_for_text_rules",
    "normal_placeholder_scope_hash",
    "structured_placeholder_scope_hash",
]
