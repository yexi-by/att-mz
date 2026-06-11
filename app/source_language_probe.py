"""注册前源语言探测。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

import aiofiles

from app.agent_toolkit.reports import AgentIssue, AgentReport, issue
from app.external_input import normalize_external_int, normalize_external_str
from app.language import SourceLanguage
from app.language_profiles import build_text_rules_setting_for_language_profile
from app.rmmz.schema import (
    COMMON_EVENTS_FILE_NAME,
    MAP_PATTERN,
    SYSTEM_FILE_NAME,
    TROOPS_FILE_NAME,
    Code,
    GameLayout,
)
from app.rmmz.loader import resolve_game_layout, validate_data_directory_integrity
from app.rmmz.source_text_detection import is_source_text_required
from app.rmmz.text_rules import JsonObject, JsonValue, TextRules, coerce_json_value, ensure_json_array, ensure_json_object

type SourceLanguageProbeClassification = Literal["ja", "en", "mixed", "other"]
type SourceLanguageProbeConfidence = Literal["high", "medium", "low"]
type SourceLanguageProbeRecommendation = SourceLanguage | Literal["uncertain"]

SOURCE_LANGUAGE_PROBE_SAMPLE_LIMIT = 12
VISIBLE_BASE_FIELDS_BY_FILE: dict[str, frozenset[str]] = {
    "Actors.json": frozenset({"name", "nickname", "profile"}),
    "Armors.json": frozenset({"name", "description"}),
    "Classes.json": frozenset({"name"}),
    "Enemies.json": frozenset({"name"}),
    "Items.json": frozenset({"name", "description"}),
    "Skills.json": frozenset({"name", "description", "message1", "message2"}),
    "States.json": frozenset({"name", "message1", "message2", "message3", "message4"}),
    "Weapons.json": frozenset({"name", "description"}),
}


@dataclass(frozen=True, slots=True)
class SourceLanguageVisibleText:
    """一条用于判断源语言的玩家可见文本。"""

    file_name: str
    location_path: str
    source_kind: str
    text: str


@dataclass(frozen=True, slots=True)
class SourceLanguageProbeSample:
    """源语言探测报告中的样本。"""

    file_name: str
    location_path: str
    source_kind: str
    text: str
    classification: SourceLanguageProbeClassification

    def to_json_object(self) -> JsonObject:
        """转换为稳定 JSON 对象。"""
        return {
            "file": self.file_name,
            "location_path": self.location_path,
            "source_kind": self.source_kind,
            "text": self.text,
            "classification": self.classification,
        }


@dataclass(frozen=True, slots=True)
class SourceLanguageProbeResult:
    """注册前源语言探测结果。"""

    game_path: Path
    content_root: Path
    engine_label: str
    recommendation: SourceLanguageProbeRecommendation
    confidence: SourceLanguageProbeConfidence
    confidence_reason: str
    visible_text_count: int
    english_text_count: int
    japanese_text_count: int
    mixed_text_count: int
    other_text_count: int
    counts_by_source_kind: dict[str, int] = field(default_factory=dict)
    samples: dict[SourceLanguageProbeClassification, list[SourceLanguageProbeSample]] = field(default_factory=dict)

    def should_block_source_language(self, source_language: SourceLanguage) -> bool:
        """判断给定源语言是否与高置信度探测结果冲突。"""
        return (
            self.confidence == "high"
            and self.recommendation != "uncertain"
            and self.recommendation != source_language
        )

    def summary_json(self) -> JsonObject:
        """生成报告摘要。"""
        return {
            "recommended_source_language": self.recommendation,
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "visible_text_count": self.visible_text_count,
            "english_text_count": self.english_text_count,
            "japanese_text_count": self.japanese_text_count,
            "mixed_text_count": self.mixed_text_count,
            "other_text_count": self.other_text_count,
            "engine": self.engine_label,
            "game_path": str(self.game_path),
            "content_root": str(self.content_root),
        }

    def details_json(self) -> JsonObject:
        """生成报告明细。"""
        return {
            "counts_by_source_kind": dict(sorted(self.counts_by_source_kind.items())),
            "samples": {
                classification: [sample.to_json_object() for sample in samples]
                for classification, samples in sorted(self.samples.items())
            },
        }

    def to_report(self) -> AgentReport:
        """转换为 AgentReport。"""
        warnings: list[AgentIssue] = []
        if self.recommendation == "uncertain":
            warnings.append(
                issue(
                    "source_language_uncertain",
                    "玩家可见文本不足或中英日信号接近，无法高置信度判断源语言；注册前需要用户确认",
                )
            )
        elif self.confidence != "high":
            warnings.append(
                issue(
                    "source_language_low_confidence",
                    f"源语言探测建议 {self.recommendation}，但置信度为 {self.confidence}；注册前建议抽样确认",
                )
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary=self.summary_json(),
            details=self.details_json(),
        )


async def probe_source_language(game_path: str | Path) -> SourceLanguageProbeResult:
    """只基于玩家可见文本探测游戏源语言。"""
    layout = resolve_game_layout(game_path)
    validate_data_directory_integrity(data_dir=layout.data_dir, role="激活数据目录")
    json_files = await _read_standard_json_files(layout)
    visible_texts = _collect_visible_texts(json_files)
    return _build_probe_result(layout=layout, visible_texts=visible_texts)


async def build_source_language_probe_report(game_path: str | Path) -> AgentReport:
    """生成源语言探测 Agent 报告。"""
    result = await probe_source_language(game_path)
    return result.to_report()


async def _read_standard_json_files(layout: GameLayout) -> dict[str, JsonValue]:
    """读取源语言探测需要的标准 data JSON 文件。"""
    data_files: dict[str, JsonValue] = {}
    paths = sorted(
        (
            file_path
            for file_path in layout.data_dir.glob("*.json")
            if file_path.is_file() and _should_read_probe_file(file_path.name)
        ),
        key=lambda path: path.name,
    )
    for file_path in paths:
        data_files[file_path.name] = await _read_json_file(file_path)
    return data_files


async def _read_json_file(file_path: Path) -> JsonValue:
    """按 UTF-8 读取 JSON 文件。"""
    async with aiofiles.open(file_path, "r", encoding="utf-8") as file:
        content = await file.read()
    return coerce_json_value(cast(object, json.loads(content)))


def _should_read_probe_file(file_name: str) -> bool:
    """判断文件是否属于源语言探测的标准可见文本范围。"""
    return (
        file_name == SYSTEM_FILE_NAME
        or file_name == COMMON_EVENTS_FILE_NAME
        or file_name == TROOPS_FILE_NAME
        or MAP_PATTERN.fullmatch(file_name) is not None
        or file_name in VISIBLE_BASE_FIELDS_BY_FILE
    )


def _collect_visible_texts(json_files: dict[str, JsonValue]) -> list[SourceLanguageVisibleText]:
    """收集玩家可见文本，不读取资源名、公式、脚本或插件内部字段。"""
    texts: list[SourceLanguageVisibleText] = []
    for file_name, value in sorted(json_files.items()):
        if file_name == SYSTEM_FILE_NAME:
            _collect_system_texts(file_name=file_name, value=value, texts=texts)
        elif file_name == COMMON_EVENTS_FILE_NAME or file_name == TROOPS_FILE_NAME or MAP_PATTERN.fullmatch(file_name):
            _collect_event_command_texts(file_name=file_name, value=value, texts=texts)
            if MAP_PATTERN.fullmatch(file_name):
                _collect_map_display_name(file_name=file_name, value=value, texts=texts)
        else:
            _collect_base_item_texts(file_name=file_name, value=value, texts=texts)
    return texts


def _collect_system_texts(
    *,
    file_name: str,
    value: JsonValue,
    texts: list[SourceLanguageVisibleText],
) -> None:
    """收集 System.json 中玩家可见系统词汇。"""
    system = ensure_json_object(value, file_name)
    _append_visible_text(texts, file_name, "System.json/gameTitle", "system_text", system.get("gameTitle"))
    terms_value = system.get("terms")
    if isinstance(terms_value, dict):
        for section_name in ("basic", "commands", "params"):
            section = terms_value.get(section_name)
            if not isinstance(section, list):
                continue
            for index, item in enumerate(section):
                _append_visible_text(
                    texts,
                    file_name,
                    f"System.json/terms/{section_name}/{index}",
                    "system_text",
                    item,
                )
        messages = terms_value.get("messages")
        if isinstance(messages, dict):
            for key, item in sorted(messages.items()):
                _append_visible_text(texts, file_name, f"System.json/terms/messages/{key}", "system_text", item)
    for section_name in ("elements", "skillTypes", "weaponTypes", "armorTypes", "equipTypes"):
        section = system.get(section_name)
        if not isinstance(section, list):
            continue
        for index, item in enumerate(section):
            _append_visible_text(texts, file_name, f"System.json/{section_name}/{index}", "system_text", item)


def _collect_base_item_texts(
    *,
    file_name: str,
    value: JsonValue,
    texts: list[SourceLanguageVisibleText],
) -> None:
    """收集基础数据库中的玩家可见字段。"""
    visible_fields = VISIBLE_BASE_FIELDS_BY_FILE.get(file_name, frozenset())
    if not visible_fields:
        return
    items = ensure_json_array(value, file_name)
    for item_index, item in enumerate(items):
        if item is None:
            continue
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        item_id = (
            normalize_external_int(raw_id, f"{file_name}[{item_index}].id")
            if raw_id is not None
            else item_index
        )
        for field_name in sorted(visible_fields):
            _append_visible_text(
                texts,
                file_name,
                f"{file_name}/{item_id}/{field_name}",
                "database_text",
                item.get(field_name),
            )


def _collect_map_display_name(
    *,
    file_name: str,
    value: JsonValue,
    texts: list[SourceLanguageVisibleText],
) -> None:
    """收集地图显示名。"""
    map_object = ensure_json_object(value, file_name)
    _append_visible_text(texts, file_name, f"{file_name}/displayName", "map_display_name", map_object.get("displayName"))


def _collect_event_command_texts(
    *,
    file_name: str,
    value: JsonValue,
    texts: list[SourceLanguageVisibleText],
) -> None:
    """收集事件指令中的玩家可见文本。"""
    for list_path, command_list in _iter_command_lists(value=value, current_path=file_name):
        for command_index, command in enumerate(command_list):
            if not isinstance(command, dict):
                continue
            code_value = command.get("code")
            if code_value is None:
                continue
            location_prefix = f"{list_path}/{command_index}"
            code = normalize_external_int(code_value, f"{location_prefix}/code")
            parameters = command.get("parameters")
            if not isinstance(parameters, list):
                continue
            if code == Code.TEXT:
                _append_visible_text(texts, file_name, location_prefix, "event_text", _list_get(parameters, 0))
            elif code == Code.SCROLL_TEXT:
                _append_visible_text(texts, file_name, location_prefix, "event_scroll_text", _list_get(parameters, 0))
            elif code == Code.CHOICES:
                choices = _list_get(parameters, 0)
                if not isinstance(choices, list):
                    continue
                for choice_index, choice in enumerate(choices):
                    _append_visible_text(
                        texts,
                        file_name,
                        f"{location_prefix}/choice/{choice_index}",
                        "event_choice",
                        choice,
                    )
            elif code == Code.NAME:
                _append_visible_text(texts, file_name, f"{location_prefix}/name", "event_namebox", _list_get(parameters, 4))


def _iter_command_lists(
    *,
    value: JsonValue,
    current_path: str,
) -> list[tuple[str, list[JsonValue]]]:
    """递归列出标准事件 command list。"""
    command_lists: list[tuple[str, list[JsonValue]]] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            command_lists.extend(_iter_command_lists(value=item, current_path=f"{current_path}/{index}"))
        return command_lists
    if not isinstance(value, dict):
        return command_lists
    list_value = value.get("list")
    if isinstance(list_value, list):
        command_lists.append((f"{current_path}/list", list_value))
    for key in ("events", "pages"):
        children = value.get(key)
        if not isinstance(children, list):
            continue
        for index, child in enumerate(children):
            command_lists.extend(_iter_command_lists(value=child, current_path=f"{current_path}/{key}/{index}"))
    return command_lists


def _append_visible_text(
    texts: list[SourceLanguageVisibleText],
    file_name: str,
    location_path: str,
    source_kind: str,
    value: JsonValue | object,
) -> None:
    """把非空字符串加入可见文本集合。"""
    if value is None:
        return
    normalized_text = normalize_external_str(value, location_path).strip()
    if not normalized_text:
        return
    texts.append(
        SourceLanguageVisibleText(
            file_name=file_name,
            location_path=location_path,
            source_kind=source_kind,
            text=normalized_text,
        )
    )


def _list_get(items: list[JsonValue], index: int) -> JsonValue | None:
    """安全读取 JSON 数组项。"""
    if index < 0 or index >= len(items):
        return None
    return items[index]


def _build_probe_result(
    *,
    layout: GameLayout,
    visible_texts: list[SourceLanguageVisibleText],
) -> SourceLanguageProbeResult:
    """按可见文本集合构造探测结果。"""
    ja_rules = TextRules.from_setting(build_text_rules_setting_for_language_profile("ja"))
    en_rules = TextRules.from_setting(build_text_rules_setting_for_language_profile("en"))
    counts_by_classification: dict[SourceLanguageProbeClassification, int] = {
        "ja": 0,
        "en": 0,
        "mixed": 0,
        "other": 0,
    }
    counts_by_source_kind: dict[str, int] = {}
    samples: dict[SourceLanguageProbeClassification, list[SourceLanguageProbeSample]] = {
        "ja": [],
        "en": [],
        "mixed": [],
        "other": [],
    }
    for visible_text in visible_texts:
        classification = _classify_visible_text(
            text=visible_text.text,
            ja_rules=ja_rules,
            en_rules=en_rules,
        )
        counts_by_classification[classification] += 1
        counts_by_source_kind[visible_text.source_kind] = counts_by_source_kind.get(visible_text.source_kind, 0) + 1
        if len(samples[classification]) < SOURCE_LANGUAGE_PROBE_SAMPLE_LIMIT:
            samples[classification].append(
                SourceLanguageProbeSample(
                    file_name=visible_text.file_name,
                    location_path=visible_text.location_path,
                    source_kind=visible_text.source_kind,
                    text=visible_text.text,
                    classification=classification,
                )
            )

    recommendation, confidence, reason = _recommend_source_language(
        english_text_count=counts_by_classification["en"],
        japanese_text_count=counts_by_classification["ja"],
        mixed_text_count=counts_by_classification["mixed"],
        visible_text_count=len(visible_texts),
    )
    return SourceLanguageProbeResult(
        game_path=layout.game_root,
        content_root=layout.content_root,
        engine_label=layout.engine_label,
        recommendation=recommendation,
        confidence=confidence,
        confidence_reason=reason,
        visible_text_count=len(visible_texts),
        english_text_count=counts_by_classification["en"],
        japanese_text_count=counts_by_classification["ja"],
        mixed_text_count=counts_by_classification["mixed"],
        other_text_count=counts_by_classification["other"],
        counts_by_source_kind=counts_by_source_kind,
        samples=samples,
    )


def _classify_visible_text(
    *,
    text: str,
    ja_rules: TextRules,
    en_rules: TextRules,
) -> SourceLanguageProbeClassification:
    """按日文/英文语言档案分类单条可见文本。"""
    has_ja_signal = _contains_required_source_text(text=text, rules=ja_rules)
    has_en_signal = _contains_required_source_text(text=text, rules=en_rules)
    if has_ja_signal and has_en_signal:
        return "mixed"
    if has_ja_signal:
        return "ja"
    if has_en_signal:
        return "en"
    return "other"


def _contains_required_source_text(*, text: str, rules: TextRules) -> bool:
    """只按源语言字符规则判断玩家可见文本，避免把断词对白当协议噪音。"""
    return is_source_text_required(rules, text, apply_exclusion_profile=False)


def _recommend_source_language(
    *,
    english_text_count: int,
    japanese_text_count: int,
    mixed_text_count: int,
    visible_text_count: int,
) -> tuple[SourceLanguageProbeRecommendation, SourceLanguageProbeConfidence, str]:
    """根据分类计数给出源语言建议。"""
    if visible_text_count == 0:
        return "uncertain", "low", "未发现玩家可见文本"
    english_score = english_text_count + mixed_text_count
    japanese_score = japanese_text_count + mixed_text_count
    if english_score == 0 and japanese_score == 0:
        return "uncertain", "low", "玩家可见文本中没有日文或英文信号"
    if english_text_count == 0 and japanese_text_count == 0 and mixed_text_count > 0:
        return "uncertain", "low", "可见文本同时含日文和英文信号，无法判断主源语言"

    if english_score >= max(5, japanese_score * 3):
        return "en", "high", "英文可见文本数量明显高于日文"
    if japanese_score >= max(5, english_score * 3):
        return "ja", "high", "日文可见文本数量明显高于英文"
    if english_score >= max(3, japanese_score * 2):
        return "en", "medium", "英文可见文本数量高于日文，但优势不够强"
    if japanese_score >= max(3, english_score * 2):
        return "ja", "medium", "日文可见文本数量高于英文，但优势不够强"
    return "uncertain", "low", "日文和英文可见文本信号接近"


__all__ = [
    "SourceLanguageProbeResult",
    "SourceLanguageProbeSample",
    "SourceLanguageVisibleText",
    "build_source_language_probe_report",
    "probe_source_language",
]
