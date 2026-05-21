"""翻译与写入前置硬闸。

本模块把 Skill 中“必须先完成”的步骤固化为程序不变量。翻译、质量报告和写入游戏文件
都应复用这里的检查，避免不同入口各写一套宽松判断。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.agent_toolkit.placeholder_scan import (
    count_uncovered_candidates,
    placeholder_candidates_to_details,
    scan_placeholder_candidates,
)
from app.config.schemas import Setting
from app.event_command_text import resolve_event_command_codes
from app.note_tag_text.exporter import collect_note_tag_candidates
from app.persistence import TargetGameSession
from app.plugin_text import collect_plugin_json_string_leaf_candidates, extract_plugin_name
from app.rmmz.commands import iter_all_commands
from app.rmmz.control_codes import StructuredPlaceholderRule
from app.rmmz.mv_namebox import mv_virtual_namebox_candidate_details
from app.rmmz.schema import GameData, TranslationData, TranslationItem
from app.rmmz.text_rules import JsonArray, JsonValue, TextRules
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    RuleReviewDomain,
    event_command_rule_scope_hash_for_codes,
    mv_virtual_namebox_rule_scope_hash,
    note_tag_rule_scope_hash_for_candidates,
    placeholder_rule_scope_hash,
    plugin_rule_scope_hash,
    structured_placeholder_rule_scope_hash,
)
from app.terminology import collect_terminology_bundle_errors
from app.text_scope import TextScopeResult, TextScopeService, read_fresh_plugin_text_rules


@dataclass(frozen=True, slots=True)
class WorkflowGateIssue:
    """单个会阻断翻译或写入的流程前置错误。"""

    code: str
    message: str


async def collect_workflow_gate_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
    custom_placeholder_rules_supplied: bool,
    translated_items: list[TranslationItem] | None = None,
    scope: TextScopeResult | None = None,
) -> list[WorkflowGateIssue]:
    """收集当前游戏不能继续翻译或写入的全部硬闸错误。"""
    if scope is None:
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
            translated_items=translated_items,
        )
    errors: list[WorkflowGateIssue] = []
    errors.extend(await _terminology_gate_errors(session))
    errors.extend(
        await _external_rule_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
        )
    )
    errors.extend(
        await _placeholder_gate_errors(
            session=session,
            scope=scope,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
        )
    )
    errors.extend(await _structured_placeholder_gate_errors(session=session, scope=scope, text_rules=text_rules))
    errors.extend(_text_scope_gate_errors(scope=scope, text_rules=text_rules))
    _ = setting
    return errors


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
    )
    if errors:
        raise RuntimeError(format_workflow_gate_error(errors))


def ensure_empty_rule_import_allowed(
    *,
    rule_label: str,
    confirm_empty: bool,
    candidate_count: int,
) -> None:
    """校验空规则导入是否经过显式确认且当前候选确实为空。"""
    if not confirm_empty:
        raise RuntimeError(f"{rule_label}为空，必须先确认当前游戏确实没有对应候选，再传 --confirm-empty")
    if candidate_count > 0:
        raise RuntimeError(f"{rule_label}为空，但当前扫描仍有 {candidate_count} 个候选，不能保存为空规则")


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
        default_command_codes=setting.event_command_text.default_codes_for_engine(game_data.layout.engine_kind),
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
    candidates = collect_note_tag_candidates(game_data=game_data, text_rules=text_rules)
    return _candidate_int_sum(candidates, "translatable_hit_count")


def note_tag_rule_scope_hash_for_text_rules(*, game_data: GameData, text_rules: TextRules) -> str:
    """按当前文本规则计算 Note 标签空规则确认范围哈希。"""
    candidates = collect_note_tag_candidates(game_data=game_data, text_rules=text_rules)
    return note_tag_rule_scope_hash_for_candidates(candidates)


def normal_placeholder_scope_hash(
    *,
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
) -> str:
    """计算普通占位符空规则确认依赖的当前候选哈希。"""
    candidates = scan_placeholder_candidates(translation_data_map, text_rules)
    return placeholder_rule_scope_hash(placeholder_candidates_to_details(candidates))


def structured_placeholder_scope_hash(
    *,
    translation_data_map: dict[str, TranslationData],
    structured_rules: tuple[StructuredPlaceholderRule, ...],
) -> str:
    """计算结构化占位符空规则确认依赖的当前候选哈希。"""
    details = collect_structured_placeholder_candidate_details(
        translation_data_map=translation_data_map,
        structured_rules=structured_rules,
    )
    return structured_placeholder_rule_scope_hash(details)


def count_uncovered_structured_placeholder_candidates(
    *,
    translation_data_map: dict[str, TranslationData],
    structured_rules: tuple[StructuredPlaceholderRule, ...],
) -> int:
    """统计未被结构化规则覆盖的协议外壳候选数量。"""
    details = collect_structured_placeholder_candidate_details(
        translation_data_map=translation_data_map,
        structured_rules=structured_rules,
    )
    return sum(
        1
        for detail in details
        if isinstance(detail, dict) and detail.get("covered") is not True
    )


def collect_structured_placeholder_candidate_details(
    *,
    translation_data_map: dict[str, TranslationData],
    structured_rules: tuple[StructuredPlaceholderRule, ...],
) -> JsonArray:
    """扫描当前正文中的结构化协议外壳候选和规则覆盖情况。"""
    details: JsonArray = []
    seen_candidates: set[tuple[str, int, int, int, str]] = set()
    for item in _iter_translation_items_from_map(translation_data_map):
        for line_index, line in enumerate(item.original_lines):
            covered_ranges = _structured_rule_covered_ranges(text=line, structured_rules=structured_rules)
            for start, end, candidate in _iter_structured_shell_candidate_matches(line):
                key = (item.location_path, line_index, start, end, candidate)
                if key in seen_candidates:
                    continue
                seen_candidates.add(key)
                matching_rules = [
                    rule_name
                    for range_start, range_end, rule_name in covered_ranges
                    if range_start <= start and range_end >= end
                ]
                details.append(
                    {
                        "location_path": item.location_path,
                        "line_number": line_index + 1,
                        "candidate": candidate,
                        "covered": bool(matching_rules),
                        "matching_rules": [rule_name for rule_name in matching_rules],
                    }
                )
    return details


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
                    current_scope_hash=mv_virtual_namebox_rule_scope_hash(
                        mv_virtual_namebox_candidate_details(game_data)
                    ),
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


async def _placeholder_gate_errors(
    *,
    session: TargetGameSession,
    scope: TextScopeResult,
    text_rules: TextRules,
    custom_placeholder_rules_supplied: bool,
) -> list[WorkflowGateIssue]:
    """检查普通自定义占位符规则是否覆盖当前正文候选。"""
    candidates = scan_placeholder_candidates(scope.translation_data_map, text_rules)
    uncovered_count = count_uncovered_candidates(candidates)
    errors: list[WorkflowGateIssue] = []
    if uncovered_count:
        errors.append(
            WorkflowGateIssue(
                code="placeholder_uncovered",
                message=f"发现 {uncovered_count} 个未覆盖的疑似自定义控制符，请先导入普通占位符规则",
            )
        )
    if custom_placeholder_rules_supplied:
        return errors
    placeholder_records = await session.read_placeholder_rules()
    if placeholder_records:
        return errors
    current_scope_hash = placeholder_rule_scope_hash(placeholder_candidates_to_details(candidates))
    errors.extend(
        await _empty_rule_review_errors(
            session=session,
            rule_domain=PLACEHOLDER_RULE_DOMAIN,
            current_scope_hash=current_scope_hash,
            label="普通占位符规则",
        )
    )
    return errors


async def _structured_placeholder_gate_errors(
    *,
    session: TargetGameSession,
    scope: TextScopeResult,
    text_rules: TextRules,
) -> list[WorkflowGateIssue]:
    """检查结构化占位符规则是否覆盖当前正文候选。"""
    structured_details = collect_structured_placeholder_candidate_details(
        translation_data_map=scope.translation_data_map,
        structured_rules=text_rules.structured_placeholder_rules,
    )
    uncovered_count = sum(
        1
        for detail in structured_details
        if isinstance(detail, dict) and detail.get("covered") is not True
    )
    errors: list[WorkflowGateIssue] = []
    if uncovered_count:
        errors.append(
            WorkflowGateIssue(
                code="structured_placeholder_uncovered",
                message=f"发现 {uncovered_count} 个未被结构化规则覆盖的协议外壳候选，请先导入结构化占位符规则",
            )
        )
    structured_records = await session.read_structured_placeholder_rules()
    if structured_records:
        return errors
    current_scope_hash = structured_placeholder_rule_scope_hash(structured_details)
    errors.extend(
        await _empty_rule_review_errors(
            session=session,
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            current_scope_hash=current_scope_hash,
            label="结构化占位符规则",
        )
    )
    return errors


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
    state = await session.read_rule_review_state(rule_domain=rule_domain)
    if state is None or not state.reviewed_empty:
        return [
            WorkflowGateIssue(
                code=f"{rule_domain}_missing",
                message=f"{label}为空且没有显式确认当前游戏没有对应规则，检查没通过，不能继续",
            )
        ]
    if state.scope_hash != current_scope_hash:
        return [
            WorkflowGateIssue(
                code=f"{rule_domain}_stale_empty_confirmation",
                message=f"{label}曾确认为空，但当前游戏内容已经变化，请重新扫描并导入规则",
            )
        ]
    return []


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


STRUCTURED_SHELL_CANDIDATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<[^<>\r\n]{1,160}(?:[:：=])[^<>\r\n]{0,240}>"),
    re.compile(r"◆<[^<>\r\n]{1,160}>[^\s<>\r\n]?"),
    re.compile(r"【[^】\r\n]{1,160}[:：][^】\r\n]{0,240}】"),
)


def _iter_translation_items_from_map(translation_data_map: dict[str, TranslationData]) -> list[TranslationItem]:
    """从正文提取结果中取出翻译条目。"""
    items: list[TranslationItem] = []
    for translation_data in translation_data_map.values():
        items.extend(translation_data.translation_items)
    return items


def _iter_structured_shell_candidate_matches(text: str) -> list[tuple[int, int, str]]:
    """扫描常见结构化协议外壳候选。"""
    matches: list[tuple[int, int, str]] = []
    for pattern in STRUCTURED_SHELL_CANDIDATE_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), match.group(0)))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))

    selected: list[tuple[int, int, str]] = []
    protected_until = -1
    for start, end, candidate in matches:
        if start < protected_until:
            continue
        selected.append((start, end, candidate))
        protected_until = end
    return selected


def _structured_rule_covered_ranges(
    *,
    text: str,
    structured_rules: tuple[StructuredPlaceholderRule, ...],
) -> list[tuple[int, int, str]]:
    """返回结构化规则完整命中范围。"""
    ranges: list[tuple[int, int, str]] = []
    for rule in structured_rules:
        for match in rule.pattern.finditer(text):
            ranges.append((match.start(), match.end(), rule.rule_name))
    return ranges


__all__: list[str] = [
    "WorkflowGateIssue",
    "collect_external_text_rule_gate_errors",
    "assert_workflow_gate_passed",
    "collect_structured_placeholder_candidate_details",
    "collect_workflow_gate_errors",
    "count_event_command_rule_candidates_for_codes",
    "event_command_rule_scope_hash_for_setting",
    "event_command_rule_codes_for_setting",
    "event_command_rule_scope_hash_for_command_codes",
    "count_event_command_rule_candidates",
    "count_note_tag_rule_candidates",
    "count_plugin_rule_candidates",
    "count_uncovered_structured_placeholder_candidates",
    "ensure_empty_rule_import_allowed",
    "format_workflow_gate_error",
    "note_tag_rule_scope_hash_for_text_rules",
    "normal_placeholder_scope_hash",
    "structured_placeholder_scope_hash",
]
