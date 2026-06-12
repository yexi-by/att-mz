"""插件、事件指令、Note 标签和文本规则记录会话能力。"""

import json
from dataclasses import dataclass
from typing import cast

from app.rule_review import (
    RuleReviewDomain,
    rule_review_domain_for_runtime_domain,
    rule_runtime_domain_for_review_domain,
)
from app.rmmz.json_types import JsonObject, coerce_json_value, ensure_json_object
from app.rmmz.schema import (
    EventCommandParameterFilter,
    EventCommandTextRuleRecord,
    MvVirtualNameboxRuleRecord,
    MvVirtualNameboxSpeakerPolicy,
    NonstandardDataTextRuleRecord,
    NoteTagTextRuleRecord,
    PlaceholderRuleRecord,
    PluginSourceTextRuleRecord,
    PluginTextRuleRecord,
    SourceResidualRuleRecord,
    StructuredPlaceholderRuleRecord,
)

from .records import RuleReviewStateRecord
from .rows import row_int, row_str
from .session_base import SessionMixinBase
from .session_utils import parse_source_residual_rule_type
from .sql import (
    SELECT_RULES_BY_DOMAIN,
    SELECT_RULE_REVIEW_STATE,
)


@dataclass(frozen=True, slots=True)
class _RuntimeRuleRow:
    """从统一规则表读取的一条规则。"""

    rule_order: int
    matcher_kind: str
    matcher_value: str
    payload_json: JsonObject


def _payload_from_text(value: str, *, db_path: object, context: str) -> JsonObject:
    """把 rules.payload_json 收窄为当前 JSON 对象。"""
    try:
        return ensure_json_object(coerce_json_value(cast(object, json.loads(value))), context)
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{context} 必须是 JSON 对象: {db_path}") from error


def _required_string(payload: JsonObject, field: str, *, db_path: object, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise RuntimeError(f"{context}.{field} 必须是字符串: {db_path}")
    return value


def _optional_string(payload: JsonObject, field: str, default: str = "") -> str:
    value = payload.get(field)
    if isinstance(value, str):
        return value
    return default


def _required_int(payload: JsonObject, field: str, *, db_path: object, context: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int):
        raise RuntimeError(f"{context}.{field} 必须是整数: {db_path}")
    return value


def _string_list(payload: JsonObject, field: str, *, db_path: object, context: str) -> list[str]:
    value = payload.get(field, [])
    if not isinstance(value, list):
        raise RuntimeError(f"{context}.{field} 必须是字符串数组: {db_path}")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise RuntimeError(f"{context}.{field}[{index}] 必须是字符串: {db_path}")
        result.append(item)
    return result


def _string_map(payload: JsonObject, field: str, *, db_path: object, context: str) -> dict[str, str]:
    value = payload.get(field, {})
    if not isinstance(value, dict):
        raise RuntimeError(f"{context}.{field} 必须是字符串对象: {db_path}")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise RuntimeError(f"{context}.{field}.{key} 必须是字符串: {db_path}")
        result[key] = item
    return result


def _event_parameter_filters(payload: JsonObject, *, db_path: object) -> list[EventCommandParameterFilter]:
    value = payload.get("parameter_filters", [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"rules.payload_json.parameter_filters 必须是数组: {db_path}")
    result: list[EventCommandParameterFilter] = []
    for item_index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RuntimeError(f"rules.payload_json.parameter_filters[{item_index}] 必须是对象: {db_path}")
        item_object = ensure_json_object(
            coerce_json_value(cast(object, item)),
            "rules.payload_json.parameter_filters[]",
        )
        result.append(
            EventCommandParameterFilter(
                index=_required_int(
                    item_object,
                    "index",
                    db_path=db_path,
                    context="rules.payload_json.parameter_filters[]",
                ),
                value=_required_string(
                    item_object,
                    "value",
                    db_path=db_path,
                    context="rules.payload_json.parameter_filters[]",
                ),
            )
        )
    return result


class RuleRecordSessionMixin(SessionMixinBase):
    """负责当前游戏规则记录的读取与数据库值收窄。"""

    async def _read_runtime_rules(self, *, domain: str) -> list[_RuntimeRuleRow]:
        """读取某个 rule_runtime domain 的统一规则。"""
        async with self.connection.execute(SELECT_RULES_BY_DOMAIN, (domain,)) as cursor:
            rows = await cursor.fetchall()
        rules: list[_RuntimeRuleRow] = []
        for row in rows:
            if row_int(row, "enabled", self.db_path) != 1:
                continue
            rules.append(
                _RuntimeRuleRow(
                    rule_order=row_int(row, "rule_order", self.db_path),
                    matcher_kind=row_str(row, "matcher_kind", self.db_path),
                    matcher_value=row_str(row, "matcher_value", self.db_path),
                    payload_json=_payload_from_text(
                        row_str(row, "payload_json", self.db_path),
                        db_path=self.db_path,
                        context="rules.payload_json",
                    ),
                )
            )
        return rules

    async def read_plugin_text_rules(self) -> list[PluginTextRuleRecord]:
        """读取当前游戏保存的全部插件文本规则。"""
        rows = await self._read_runtime_rules(domain="plugin_config")
        grouped_records: dict[int, PluginTextRuleRecord] = {}
        for row in rows:
            payload = row.payload_json
            plugin_index = _required_int(payload, "plugin_index", db_path=self.db_path, context="rules.payload_json")
            record = grouped_records.get(plugin_index)
            if record is None:
                record = PluginTextRuleRecord(
                    plugin_index=plugin_index,
                    plugin_name=_required_string(
                        payload,
                        "plugin_name",
                        db_path=self.db_path,
                        context="rules.payload_json",
                    ),
                    plugin_hash=_optional_string(payload, "plugin_hash"),
                    path_templates=[],
                )
                grouped_records[plugin_index] = record
            record.path_templates.append(_optional_string(payload, "path", row.matcher_value))
        return [grouped_records[key] for key in sorted(grouped_records)]

    async def read_plugin_source_text_rules(self) -> list[PluginSourceTextRuleRecord]:
        """读取当前游戏保存的插件源码文本规则。"""
        rows = await self._read_runtime_rules(domain="plugin_source")
        grouped_records: dict[str, PluginSourceTextRuleRecord] = {}
        for row in rows:
            payload = row.payload_json
            file_name = _optional_string(payload, "file_name", _optional_string(payload, "file"))
            if not file_name:
                raise RuntimeError(f"rules.payload_json.file_name 必须是字符串: {self.db_path}")
            record = grouped_records.get(file_name)
            if record is None:
                record = PluginSourceTextRuleRecord(
                    file_name=file_name,
                    file_hash=_optional_string(payload, "file_hash"),
                    selectors=[],
                    excluded_selectors=[],
                )
                grouped_records[file_name] = record
            selector = _optional_string(payload, "selector", row.matcher_value)
            selector_kind = _optional_string(payload, "selector_kind", "translate")
            if selector_kind == "translate":
                record.selectors.append(selector)
            elif selector_kind == "excluded":
                record.excluded_selectors.append(selector)
            else:
                raise RuntimeError(f"插件源码规则 selector 类型无效: {selector_kind}")
        return [grouped_records[key] for key in sorted(grouped_records)]

    async def read_nonstandard_data_text_rules(self) -> list[NonstandardDataTextRuleRecord]:
        """读取当前游戏保存的非标准 data 文件文本规则。"""
        rows = await self._read_runtime_rules(domain="nonstandard_data")
        grouped_records: dict[str, NonstandardDataTextRuleRecord] = {}
        for row in rows:
            payload = row.payload_json
            file_name = _optional_string(payload, "file_name", _optional_string(payload, "file"))
            if not file_name:
                raise RuntimeError(f"rules.payload_json.file_name 必须是字符串: {self.db_path}")
            file_hash = _optional_string(payload, "file_hash")
            record = grouped_records.get(file_name)
            if record is None:
                record = NonstandardDataTextRuleRecord(
                    file_name=file_name,
                    file_hash=file_hash,
                    path_templates=[],
                    excluded_path_templates=[],
                    skipped=False,
                )
                grouped_records[file_name] = record
            elif record.file_hash != file_hash:
                raise RuntimeError(f"非标准 data 规则文件哈希不一致，请重新导入规则: {file_name}")
            path_template = _optional_string(payload, "path", row.matcher_value)
            path_kind = _optional_string(payload, "path_kind", _optional_string(payload, "rule_type", "translate"))
            if path_kind == "translated":
                path_kind = "translate"
            if path_kind == "translate":
                record.path_templates.append(path_template)
            elif path_kind == "excluded":
                record.excluded_path_templates.append(path_template)
            elif path_kind == "skipped":
                if path_template:
                    raise RuntimeError(f"非标准 data 跳过规则不应包含路径，请重新导入规则: {file_name}")
                record.skipped = True
            else:
                raise RuntimeError(f"非标准 data 规则 path_kind 非法，请重新导入规则: {path_kind}")
        return [grouped_records[key] for key in sorted(grouped_records)]

    async def read_note_tag_text_rules(self) -> list[NoteTagTextRuleRecord]:
        """读取当前游戏保存的 Note 标签文本规则。"""
        rows = await self._read_runtime_rules(domain="note_tags")
        grouped_records: dict[str, NoteTagTextRuleRecord] = {}
        for row in rows:
            payload = row.payload_json
            file_name = _required_string(payload, "file_name", db_path=self.db_path, context="rules.payload_json")
            record = grouped_records.get(file_name)
            if record is None:
                record = NoteTagTextRuleRecord(file_name=file_name, tag_names=[])
                grouped_records[file_name] = record
            record.tag_names.append(_required_string(payload, "tag_name", db_path=self.db_path, context="rules.payload_json"))
        return [grouped_records[key] for key in sorted(grouped_records)]

    async def read_event_command_text_rules(self) -> list[EventCommandTextRuleRecord]:
        """读取当前游戏保存的事件指令文本规则。"""
        rows = await self._read_runtime_rules(domain="event_commands")
        grouped_records: dict[tuple[int, tuple[tuple[int, str], ...]], EventCommandTextRuleRecord] = {}
        for row in rows:
            payload = row.payload_json
            command_code = _required_int(payload, "command_code", db_path=self.db_path, context="rules.payload_json")
            parameter_filters = _event_parameter_filters(payload, db_path=self.db_path)
            group_key = (
                command_code,
                tuple((item.index, item.value) for item in parameter_filters),
            )
            record = grouped_records.get(group_key)
            if record is None:
                record = EventCommandTextRuleRecord(
                    command_code=command_code,
                    parameter_filters=parameter_filters,
                    path_templates=[],
                )
                grouped_records[group_key] = record
            record.path_templates.append(_optional_string(payload, "path", row.matcher_value))
        return [grouped_records[key] for key in sorted(grouped_records)]

    async def read_placeholder_rules(self) -> list[PlaceholderRuleRecord]:
        """读取当前游戏专用自定义占位符规则。"""
        rows = await self._read_runtime_rules(domain="placeholders")
        return [
            PlaceholderRuleRecord(
                pattern_text=row.matcher_value,
                placeholder_template=_required_string(
                    row.payload_json,
                    "placeholder_template",
                    db_path=self.db_path,
                    context="rules.payload_json",
                ),
            )
            for row in rows
        ]

    async def read_structured_placeholder_rules(self) -> list[StructuredPlaceholderRuleRecord]:
        """读取当前游戏专用结构化占位符规则。"""
        rows = await self._read_runtime_rules(domain="structured_placeholders")
        return [
            StructuredPlaceholderRuleRecord(
                rule_name=_required_string(row.payload_json, "rule_name", db_path=self.db_path, context="rules.payload_json"),
                rule_type=_required_string(row.payload_json, "rule_type", db_path=self.db_path, context="rules.payload_json"),
                pattern_text=_optional_string(row.payload_json, "pattern", row.matcher_value),
                translatable_group=_required_string(
                    row.payload_json,
                    "translatable_group",
                    db_path=self.db_path,
                    context="rules.payload_json",
                ),
                protected_groups=_string_map(
                    row.payload_json,
                    "protected_groups",
                    db_path=self.db_path,
                    context="rules.payload_json",
                ),
            )
            for row in rows
        ]

    async def read_source_residual_rules(self) -> list[SourceResidualRuleRecord]:
        """读取当前游戏专用源文残留例外规则。"""
        rows = await self._read_runtime_rules(domain="source_residual")
        return [
            SourceResidualRuleRecord(
                rule_id=_optional_string(row.payload_json, "rule_id"),
                rule_type=parse_source_residual_rule_type(
                    _required_string(row.payload_json, "rule_type", db_path=self.db_path, context="rules.payload_json"),
                    self.db_path,
                ),
                location_path=_optional_string(row.payload_json, "location_path", row.matcher_value),
                pattern_text=_optional_string(row.payload_json, "pattern_text", row.matcher_value),
                allowed_terms=_string_list(
                    row.payload_json,
                    "allowed_terms",
                    db_path=self.db_path,
                    context="rules.payload_json",
                ),
                check_group=_optional_string(row.payload_json, "check_group"),
                reason=_required_string(row.payload_json, "reason", db_path=self.db_path, context="rules.payload_json"),
            )
            for row in rows
        ]

    async def read_mv_virtual_namebox_rules(self) -> list[MvVirtualNameboxRuleRecord]:
        """读取当前游戏专用 MV 虚拟名字框规则。"""
        rows = await self._read_runtime_rules(domain="mv_virtual_namebox")
        return [
            MvVirtualNameboxRuleRecord(
                rule_order=row.rule_order,
                rule_name=_required_string(row.payload_json, "name", db_path=self.db_path, context="rules.payload_json"),
                pattern_text=_optional_string(row.payload_json, "pattern", row.matcher_value),
                speaker_group=_required_string(row.payload_json, "speaker_group", db_path=self.db_path, context="rules.payload_json"),
                body_group=_optional_string(row.payload_json, "body_group"),
                speaker_policy=_parse_mv_virtual_namebox_speaker_policy(
                    _required_string(
                        row.payload_json,
                        "speaker_policy",
                        db_path=self.db_path,
                        context="rules.payload_json",
                    ),
                    self.db_path,
                ),
                render_template=_required_string(
                    row.payload_json,
                    "render_template",
                    db_path=self.db_path,
                    context="rules.payload_json",
                ),
            )
            for row in rows
        ]

    async def read_rule_review_state(
        self,
        *,
        rule_domain: RuleReviewDomain,
    ) -> RuleReviewStateRecord | None:
        """读取某类规则的当前候选审查确认状态。"""
        runtime_domain = rule_runtime_domain_for_review_domain(rule_domain)
        async with self.connection.execute(SELECT_RULE_REVIEW_STATE, (runtime_domain,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        state_json = row_str(row, "state_json", self.db_path)
        try:
            state = ensure_json_object(
                coerce_json_value(cast(object, json.loads(state_json))),
                "rule_domain_states.state_json",
            )
        except (TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"rule_domain_states.state_json 必须是 JSON 对象: {self.db_path}") from error
        reviewed_candidates = state.get("reviewed_candidates")
        if not isinstance(reviewed_candidates, bool):
            message = "rule_domain_states.state_json.reviewed_candidates 必须是布尔值，" + (
                f"请重新导入对应规则以生成当前契约状态: {self.db_path}"
            )
            raise RuntimeError(message)
        confirmed_empty = state.get("confirmed_empty")
        if not isinstance(confirmed_empty, bool):
            raise RuntimeError(f"rule_domain_states.state_json.confirmed_empty 必须是布尔值: {self.db_path}")
        return RuleReviewStateRecord(
            rule_domain=rule_review_domain_for_runtime_domain(row_str(row, "domain", self.db_path)),
            scope_hash=row_str(row, "scope_hash", self.db_path),
            reviewed_candidates=reviewed_candidates,
            confirmed_empty=confirmed_empty,
            updated_at=row_str(row, "confirmed_at", self.db_path),
        )


def _parse_mv_virtual_namebox_speaker_policy(value: str, db_path: object) -> MvVirtualNameboxSpeakerPolicy:
    """校验数据库中的 MV 虚拟名字框说话人策略。"""
    if value == "translate":
        return "translate"
    if value == "preserve":
        return "preserve"
    if value == "actor_name":
        return "actor_name"
    raise RuntimeError(f"rules.payload_json.speaker_policy 非法，请重新导入规则: {db_path}")
