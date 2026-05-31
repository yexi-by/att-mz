"""插件源码文本规则驱动提取。"""

from __future__ import annotations

from app.rmmz.schema import GameData, PluginSourceTextRuleRecord, TranslationData, TranslationItem
from app.rmmz.text_rules import TextRules, get_default_text_rules

from .models import PluginSourceScan
from .scanner import PluginSourceCandidateIndex, build_plugin_source_candidate_index
from .rules import StalePluginSourceTextRule, filter_fresh_plugin_source_text_rules


class PluginSourceTextExtraction:
    """从已确认插件源码 AST selector 提取正文文本。"""

    def __init__(
        self,
        game_data: GameData,
        rule_records: list[PluginSourceTextRuleRecord],
        text_rules: TextRules | None = None,
        scan: PluginSourceScan | None = None,
    ) -> None:
        """初始化插件源码提取器。"""
        self.game_data: GameData = game_data
        self.rule_records: list[PluginSourceTextRuleRecord] = rule_records
        self.text_rules: TextRules = text_rules if text_rules is not None else get_default_text_rules()
        self.scan: PluginSourceScan | None = scan

    def extract_all_text(self) -> dict[str, TranslationData]:
        """按规则全量提取插件源码文本。"""
        rule_records = self._validated_rule_records()
        result: dict[str, TranslationData] = {}
        records_by_file: dict[str, list[PluginSourceTextRuleRecord]] = {}
        for record in rule_records:
            records_by_file.setdefault(record.file_name, []).append(record)
        for file_name, records in records_by_file.items():
            source = self.game_data.plugin_source_files.get(file_name)
            if source is None:
                raise RuntimeError(
                    f"插件源码规则已过期: {file_name}: 插件源码文件不存在，请重新导出并导入插件源码规则"
                )
            file_key = plugin_source_file_key(file_name)
            candidate_index = self._candidate_index_for_file(
                file_name=file_name,
                source=source,
            )
            items: list[TranslationItem] = []
            for record in records:
                items.extend(self._extract_file_items(record=record, candidate_index=candidate_index))
            if not items:
                continue
            result[file_key] = TranslationData(display_name=None, translation_items=items)
        return result

    def _validated_rule_records(self) -> list[PluginSourceTextRuleRecord]:
        """确认数据库插件源码规则仍然匹配当前运行源码。"""
        if not self.rule_records:
            return []
        scan = self._scan_for_validation()
        fresh_rules, stale_rules = filter_fresh_plugin_source_text_rules(
            game_data=self.game_data,
            rule_records=self.rule_records,
            text_rules=self.text_rules,
            scan=scan,
        )
        if stale_rules:
            raise RuntimeError(_format_stale_plugin_source_rule_error(stale_rules))
        return fresh_rules

    def _extract_file_items(
        self,
        *,
        record: PluginSourceTextRuleRecord,
        candidate_index: PluginSourceCandidateIndex,
    ) -> list[TranslationItem]:
        """提取单个源码文件的规则命中项。"""
        items: list[TranslationItem] = []
        for selector in record.selectors:
            candidate = candidate_index.by_selector.get(selector)
            if candidate is None:
                continue
            if not self.text_rules.should_translate_source_text(candidate.text):
                continue
            items.append(
                TranslationItem(
                    location_path=plugin_source_location_path(
                        file_name=record.file_name,
                        selector=selector,
                    ),
                    item_type="short_text",
                    original_lines=[candidate.text],
                    source_line_paths=[
                        plugin_source_location_path(file_name=record.file_name, selector=selector)
                    ],
                )
            )
        return items

    def _candidate_index_for_file(self, *, file_name: str, source: str) -> PluginSourceCandidateIndex:
        """读取已有扫描结果或为单文件构建候选索引。"""
        if self.scan is not None:
            for file_scan in self.scan.files:
                if file_scan.file_name != file_name:
                    continue
                candidates = file_scan.candidates
                return PluginSourceCandidateIndex(
                    candidates=candidates,
                    by_selector={candidate.selector: candidate for candidate in candidates},
                )
        return build_plugin_source_candidate_index(
            file_name=file_name,
            source=source,
            active=True,
            text_rules=self.text_rules,
        )

    def _scan_for_validation(self) -> PluginSourceScan:
        """读取或创建一次插件源码扫描结果。"""
        if self.scan is None:
            from .scanner import build_plugin_source_scan

            self.scan = build_plugin_source_scan(
                game_data=self.game_data,
                text_rules=self.text_rules,
            )
        return self.scan


def _format_stale_plugin_source_rule_error(
    stale_rules: list[StalePluginSourceTextRule],
) -> str:
    """把插件源码过期规则压缩成稳定错误信息。"""
    first_rule = stale_rules[0]
    suffix = "" if len(stale_rules) == 1 else f" 等 {len(stale_rules)} 个文件"
    return (
        "插件源码规则已过期: "
        f"{first_rule.file_name}{suffix}: {first_rule.reason}，"
        "请重新导出并导入插件源码规则"
    )


def plugin_source_file_key(file_name: str) -> str:
    """返回统一文本范围中的插件源码文件键。"""
    return f"js/plugins/{file_name}"


def plugin_source_location_path(*, file_name: str, selector: str) -> str:
    """返回插件源码文本内部定位键。"""
    return f"{plugin_source_file_key(file_name)}/{selector}"


def parse_plugin_source_location_path(location_path: str) -> tuple[str, str] | None:
    """从内部定位键解析插件源码文件名和 selector。"""
    prefix = "js/plugins/"
    if not location_path.startswith(prefix):
        return None
    remain = location_path[len(prefix):]
    parts = remain.split("/", 1)
    if len(parts) != 2:
        return None
    file_name, selector = parts
    if not file_name.endswith(".js") or not selector:
        return None
    return file_name, selector


__all__ = [
    "PluginSourceTextExtraction",
    "parse_plugin_source_location_path",
    "plugin_source_file_key",
    "plugin_source_location_path",
]
