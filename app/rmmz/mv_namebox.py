"""MV 虚拟名字框外部规则。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from string import Formatter
from typing import cast

from pydantic import Field, TypeAdapter, field_validator

from app.external_input import ExternalInputModel, ExternalStr
from app.native_rule_runtime import RuleRuntimeMvVirtualNameboxMatch, match_mv_virtual_namebox_rules
from app.rmmz.json_types import JsonObject, coerce_json_value, ensure_json_object
from app.rmmz.schema import (
    GameData,
    MvVirtualNameboxRuleRecord,
    MvVirtualNameboxSpeakerPolicy,
)


ACTOR_NAME_CONTROL_PATTERN: re.Pattern[str] = re.compile(r"^\\[Nn]\[(?P<actor_id>\d+)\]$")
TEMPLATE_FIELD_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_]\w*$")
MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME = "mv-virtual-namebox-rules.json"
MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME = "mv-virtual-namebox-candidates.json"


@dataclass(frozen=True, slots=True)
class MvVirtualNameboxRule:
    """已编译的 MV 虚拟名字框规则。"""

    rule_order: int
    rule_name: str
    pattern_text: str
    speaker_group: str
    body_group: str
    speaker_policy: MvVirtualNameboxSpeakerPolicy
    render_template: str

    @classmethod
    def from_record(cls, record: MvVirtualNameboxRuleRecord) -> "MvVirtualNameboxRule":
        """从数据库记录创建运行时规则。"""
        validate_rule_template_shape(
            rule_name=record.rule_name,
            speaker_group=record.speaker_group,
            body_group=record.body_group,
            render_template=record.render_template,
        )
        return cls(
            rule_order=record.rule_order,
            rule_name=record.rule_name,
            pattern_text=record.pattern_text,
            speaker_group=record.speaker_group,
            body_group=record.body_group,
            speaker_policy=record.speaker_policy,
            render_template=record.render_template,
        )


@dataclass(frozen=True, slots=True)
class MvVirtualSpeaker:
    """MV 文本首行按外部规则抽象出的虚拟名字框。"""

    speaker: str
    body_text: str
    matched_text: str
    rule_name: str
    speaker_policy: MvVirtualNameboxSpeakerPolicy
    source_speaker_text: str
    render_template: str
    group_values: dict[str, str]
    speaker_group: str
    body_group: str

    @property
    def requires_translation(self) -> bool:
        """判断说话人是否需要从字段译名表读取译名。"""
        return self.speaker_policy in {"translate", "actor_name"}

    def render(self, *, translated_speaker: str, translated_body: str | None = None) -> str:
        """按外部规则模板重建写回到 `401` 的文本。"""
        body_text = "" if translated_body is None else translated_body
        values = dict(self.group_values)
        values[self.speaker_group] = translated_speaker
        if self.body_group:
            values[self.body_group] = body_text
        values["speaker"] = translated_speaker
        values["body"] = body_text
        return self.render_template.format_map(values)

    def render_source(self) -> str:
        """按原始捕获组重建源文本，用于规则校验。"""
        body_text = self.group_values.get(self.body_group, "") if self.body_group else ""
        values = dict(self.group_values)
        values[self.speaker_group] = self.source_speaker_text
        if self.body_group:
            values[self.body_group] = body_text
        values["speaker"] = self.source_speaker_text
        values["body"] = body_text
        return self.render_template.format_map(values)


class MvVirtualNameboxRuleSpec(ExternalInputModel):
    """单条 MV 虚拟名字框外部规则。"""

    name: ExternalStr
    pattern: ExternalStr
    speaker_group: ExternalStr
    speaker_policy: MvVirtualNameboxSpeakerPolicy
    render_template: ExternalStr
    body_group: ExternalStr = ""

    @field_validator("name", "pattern", "speaker_group", "render_template")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        """必填字符串不能是空白。"""
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("必填字符串不能为空")
        return normalized_value

    @field_validator("body_group")
    @classmethod
    def _validate_body_group(cls, value: str) -> str:
        """正文分组允许省略，填写时必须清理空白。"""
        return value.strip()


class MvVirtualNameboxImportFile(ExternalInputModel):
    """MV 虚拟名字框规则导入文件。"""

    rules: list[MvVirtualNameboxRuleSpec] = Field(default_factory=list)


_MV_NAMEBOX_IMPORT_ADAPTER: TypeAdapter[MvVirtualNameboxImportFile] = TypeAdapter(
    MvVirtualNameboxImportFile
)


def parse_mv_virtual_namebox_rule_import_text(raw_text: str) -> list[MvVirtualNameboxRuleRecord]:
    """解析 MV 虚拟名字框规则 JSON 文本。"""
    import_file = parse_mv_virtual_namebox_rule_import(raw_text)
    return build_mv_virtual_namebox_rule_records(import_file.rules)


def parse_mv_virtual_namebox_rule_import_payload(raw_text: str) -> JsonObject:
    """解析 MV 虚拟名字框规则 JSON 文本并返回 rule_runtime 原始载荷。"""
    import_file = parse_mv_virtual_namebox_rule_import(raw_text)
    return ensure_json_object(
        coerce_json_value(import_file.model_dump(mode="json")),
        "mv_virtual_namebox_rule_import",
    )


def parse_mv_virtual_namebox_rule_import(raw_text: str) -> MvVirtualNameboxImportFile:
    """解析 MV 虚拟名字框规则 JSON 文本为外部导入模型。"""
    stripped_text = raw_text.strip()
    if not stripped_text:
        raise ValueError("MV 虚拟名字框规则 JSON 不能为空")
    decoded_raw = cast(object, json.loads(stripped_text))
    decoded = coerce_json_value(decoded_raw)
    return _MV_NAMEBOX_IMPORT_ADAPTER.validate_python(decoded)


def build_mv_virtual_namebox_rule_records(
    specs: list[MvVirtualNameboxRuleSpec],
) -> list[MvVirtualNameboxRuleRecord]:
    """把外部规则模型转换为数据库记录。"""
    seen_names: set[str] = set()
    records: list[MvVirtualNameboxRuleRecord] = []
    for index, spec in enumerate(specs):
        if spec.name in seen_names:
            raise ValueError(f"MV 虚拟名字框规则名重复: {spec.name}")
        seen_names.add(spec.name)
        records.append(
            MvVirtualNameboxRuleRecord(
                rule_order=index,
                rule_name=spec.name,
                pattern_text=spec.pattern,
                speaker_group=spec.speaker_group,
                body_group=spec.body_group,
                speaker_policy=spec.speaker_policy,
                render_template=spec.render_template,
            )
        )
    for record in records:
        validate_rule_template_shape(
            rule_name=record.rule_name,
            speaker_group=record.speaker_group,
            body_group=record.body_group,
            render_template=record.render_template,
        )
    return records


def validate_rule_template_shape(
    *,
    rule_name: str,
    speaker_group: str,
    body_group: str,
    render_template: str,
) -> None:
    """校验模板字段基础语法，不解释正则 capture。"""
    template_fields = read_template_fields(render_template)
    if speaker_group not in template_fields and "speaker" not in template_fields:
        raise ValueError(f"MV 虚拟名字框规则 {rule_name} 的模板没有引用说话人分组")
    if body_group and body_group not in template_fields and "body" not in template_fields:
        raise ValueError(f"MV 虚拟名字框规则 {rule_name} 的模板没有引用正文分组")


def read_template_fields(template: str) -> set[str]:
    """读取格式化模板中的字段名。"""
    fields: set[str] = set()
    for _literal_text, field_name, _format_spec, _conversion in Formatter().parse(template):
        if field_name is None:
            continue
        normalized_field = field_name.split(".", maxsplit=1)[0].split("[", maxsplit=1)[0]
        if not TEMPLATE_FIELD_PATTERN.fullmatch(normalized_field):
            raise ValueError(f"MV 虚拟名字框模板字段名非法: {field_name}")
        fields.add(normalized_field)
    return fields


def runtime_mv_virtual_namebox_rules(
    records: list[MvVirtualNameboxRuleRecord],
) -> tuple[MvVirtualNameboxRule, ...]:
    """把数据库记录转换为按顺序匹配的运行时规则。"""
    return tuple(
        MvVirtualNameboxRule.from_record(record)
        for record in sorted(records, key=lambda item: item.rule_order)
    )


def parse_mv_virtual_speaker_line(
    *,
    text: str,
    game_data: GameData,
    rules: tuple[MvVirtualNameboxRule, ...],
    location_path: str | None = None,
) -> MvVirtualSpeaker | None:
    """从 MV `401` 首条非空正文中按外部规则解析虚拟名字框。"""
    normalized_text = text.strip()
    if not normalized_text:
        return None
    matches: list[MvVirtualSpeaker] = []
    rules_by_order = {rule.rule_order: rule for rule in rules}
    for matched in _match_mv_virtual_namebox_rules(
        text=normalized_text,
        rules=rules,
    ):
        rule = rules_by_order.get(matched.rule_order)
        if rule is None:
            raise ValueError(f"MV 虚拟名字框规则命中未知规则序号: {matched.rule_order}")
        try:
            matches.append(
                _build_virtual_speaker(
                    game_data=game_data,
                    rule=rule,
                    matched_text=matched.matched_text,
                    group_values=matched.group_values,
                )
            )
        except ValueError as error:
            if location_path is None:
                raise
            raise ValueError(f"{error}; 文本路径={location_path}") from error
    if len(matches) > 1:
        rule_names = ", ".join(match.rule_name for match in matches)
        path_message = "" if location_path is None else f"; 文本路径={location_path}"
        raise ValueError(f"MV 虚拟名字框规则命中冲突{path_message}: 规则={rule_names}; 文本={normalized_text}")
    if not matches:
        return None
    return matches[0]


def mv_virtual_namebox_rule_records_to_import_json(
    records: list[MvVirtualNameboxRuleRecord] | tuple[MvVirtualNameboxRuleRecord, ...],
) -> JsonObject:
    """把数据库记录还原为外部 Agent 可编辑的规则 JSON。"""
    return {
        "rules": [
            {
                "name": record.rule_name,
                "pattern": record.pattern_text,
                "speaker_group": record.speaker_group,
                "speaker_policy": record.speaker_policy,
                "render_template": record.render_template,
                **({"body_group": record.body_group} if record.body_group else {}),
            }
            for record in sorted(records, key=lambda item: item.rule_order)
        ]
    }


def _build_virtual_speaker(
    *,
    game_data: GameData,
    rule: MvVirtualNameboxRule,
    matched_text: str,
    group_values: dict[str, str],
) -> MvVirtualSpeaker:
    """把正则命中结果转换为虚拟名字框对象。"""
    source_speaker_text = group_values[rule.speaker_group].strip()
    if not source_speaker_text:
        raise ValueError(f"MV 虚拟名字框规则 {rule.rule_name} 命中了空说话人")
    speaker = source_speaker_text
    if rule.speaker_policy == "actor_name":
        speaker = _actor_name_from_control(game_data=game_data, text=source_speaker_text)
    body_text = group_values[rule.body_group].strip() if rule.body_group else ""
    return MvVirtualSpeaker(
        speaker=speaker,
        body_text=body_text,
        matched_text=matched_text,
        rule_name=rule.rule_name,
        speaker_policy=rule.speaker_policy,
        source_speaker_text=source_speaker_text,
        render_template=rule.render_template,
        group_values=group_values,
        speaker_group=rule.speaker_group,
        body_group=rule.body_group,
    )


def _actor_name_from_control(*, game_data: GameData, text: str) -> str:
    """从 `\\N[n]` 控制符读取角色名。"""
    actor_match = ACTOR_NAME_CONTROL_PATTERN.fullmatch(text.strip())
    if actor_match is None:
        raise ValueError(f"actor_name 规则命中的说话人不是角色名控制符: {text}")
    actor_id = int(actor_match.group("actor_id"))
    for actor in game_data.base_data.get("Actors.json", []):
        if actor is None or actor.id != actor_id:
            continue
        actor_name = actor.name.strip()
        if actor_name:
            return actor_name
    raise ValueError(f"actor_name 规则无法解析角色 ID: {actor_id}")


def _match_mv_virtual_namebox_rules(
    *,
    text: str,
    rules: tuple[MvVirtualNameboxRule, ...],
) -> list[RuleRuntimeMvVirtualNameboxMatch]:
    """通过 Rust PCRE2 运行时匹配 MV 虚拟名字框规则。"""
    return match_mv_virtual_namebox_rules(
        {
            "text": text,
            "rules": [
                {
                    "rule_order": rule.rule_order,
                    "rule_name": rule.rule_name,
                    "pattern_text": rule.pattern_text,
                    "speaker_group": rule.speaker_group,
                    "body_group": rule.body_group,
                }
                for rule in rules
            ],
        }
    )


def is_actor_name_control_text(text: str) -> bool:
    """判断文本是否是 RPG Maker 标准角色名控制符。"""
    return ACTOR_NAME_CONTROL_PATTERN.fullmatch(text.strip()) is not None


__all__: list[str] = [
    "is_actor_name_control_text",
    "MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME",
    "MvVirtualNameboxRule",
    "MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME",
    "MvVirtualNameboxRuleSpec",
    "MvVirtualSpeaker",
    "mv_virtual_namebox_rule_records_to_import_json",
    "parse_mv_virtual_namebox_rule_import",
    "parse_mv_virtual_namebox_rule_import_payload",
    "parse_mv_virtual_namebox_rule_import_text",
    "parse_mv_virtual_speaker_line",
    "runtime_mv_virtual_namebox_rules",
]
