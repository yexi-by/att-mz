"""文本规则与占位符的业务测试。"""

import json
from pathlib import Path

import pytest

import app.config as config
from app.config.custom_placeholder_rules import (
    load_custom_placeholder_rules_file,
    load_custom_placeholder_rules_import_text,
    load_custom_placeholder_rules_text,
)
from app.config.structured_placeholder_rules import (
    load_structured_placeholder_rules_import_text,
    load_structured_placeholder_rules_text,
)
from app.config.schemas import TextRulesSetting
from app.language_profiles import build_text_rules_setting_for_language_profile
from app.note_tag_text.sources import note_file_pattern_matches
from app.rmmz.control_codes import (
    CustomPlaceholderRule,
    LITERAL_ESCAPE_PLACEHOLDERS,
    LITERAL_LINE_BREAK_PLACEHOLDER,
    REAL_LINE_BREAK_PLACEHOLDER,
    StructuredPlaceholderRule,
)
from app.rmmz.schema import SourceResidualRuleRecord, TranslationItem
from app.rmmz.source_text_detection import is_source_text_required
from app.rmmz.text_layout import count_line_width_chars
from app.rmmz.text_rules import TextRules, get_default_text_rules
from app.source_residual import SourceResidualRuleSet, check_source_residual_for_item
from app.translation.text_structure import validate_translation_text_structure


def _check_source_residual_lines(rules: TextRules, lines: list[str]) -> None:
    """按当前 native 源文残留契约检查无原文上下文的运行文本。"""
    item = TranslationItem(
        location_path="runtime-text",
        item_type="short_text",
        original_lines=[],
        translation_lines=lines,
    )
    check_source_residual_for_item(item=item, text_rules=rules, rule_set=None)


def test_text_rules_replace_and_restore_standard_rmmz_control_sequences() -> None:
    """全部 RMMZ 标准控制符会被占位并可恢复。"""
    rules = get_default_text_rules()
    segments = [
        "\\V[1]",
        "\\N[2]",
        "\\P[3]",
        "\\G",
        "\\C[4]",
        "\\I[5]",
        "\\{",
        "\\}",
        "\\\\",
        "\\$",
        "\\.",
        "\\|",
        "\\!",
        "\\>",
        "\\<",
        "\\^",
        "\\PX[6]",
        "\\PY[7]",
        "\\FS[8]",
        "%9",
        "\\n",
        "\\r",
        "\\t",
        "\\\"",
        "\\'",
        "\\/",
        "\\?",
        "\\a",
        "\\b",
        "\\f",
        "\\v",
        "\\x41",
        "\\u3042",
        "\\U0001F600",
        "\\012",
    ]
    placeholders = [
        "[RMMZ_VARIABLE_1]",
        "[RMMZ_ACTOR_NAME_2]",
        "[RMMZ_PARTY_MEMBER_NAME_3]",
        "[RMMZ_CURRENCY_UNIT]",
        "[RMMZ_TEXT_COLOR_4]",
        "[RMMZ_ICON_5]",
        "[RMMZ_FONT_LARGER]",
        "[RMMZ_FONT_SMALLER]",
        "[RMMZ_BACKSLASH]",
        "[RMMZ_SHOW_GOLD_WINDOW]",
        "[RMMZ_WAIT_SHORT]",
        "[RMMZ_WAIT_LONG]",
        "[RMMZ_WAIT_INPUT]",
        "[RMMZ_INSTANT_TEXT_ON]",
        "[RMMZ_INSTANT_TEXT_OFF]",
        "[RMMZ_NO_WAIT]",
        "[RMMZ_TEXT_X_POSITION_6]",
        "[RMMZ_TEXT_Y_POSITION_7]",
        "[RMMZ_FONT_SIZE_8]",
        "[RMMZ_MESSAGE_ARGUMENT_9]",
        LITERAL_LINE_BREAK_PLACEHOLDER,
        LITERAL_ESCAPE_PLACEHOLDERS["\\r"],
        LITERAL_ESCAPE_PLACEHOLDERS["\\t"],
        LITERAL_ESCAPE_PLACEHOLDERS["\\\""],
        LITERAL_ESCAPE_PLACEHOLDERS["\\'"],
        LITERAL_ESCAPE_PLACEHOLDERS["\\/"],
        LITERAL_ESCAPE_PLACEHOLDERS["\\?"],
        LITERAL_ESCAPE_PLACEHOLDERS["\\a"],
        LITERAL_ESCAPE_PLACEHOLDERS["\\b"],
        LITERAL_ESCAPE_PLACEHOLDERS["\\f"],
        LITERAL_ESCAPE_PLACEHOLDERS["\\v"],
        "[RMMZ_LITERAL_HEX_ESCAPE_5C783431]",
        "[RMMZ_LITERAL_UNICODE_ESCAPE_5C7533303432]",
        "[RMMZ_LITERAL_UNICODE_ESCAPE_5C553030303146363030]",
        "[RMMZ_LITERAL_OCTAL_ESCAPE_5C303132]",
    ]
    item = TranslationItem(
        location_path="Map001.json/1/0/0",
        item_type="long_text",
        original_lines=["こんにちは" + "".join(segments)],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == ["こんにちは" + "".join(placeholders)]

    item.translation_lines_with_placeholders = ["你好" + "".join(placeholders)]
    item.verify_placeholders(rules)
    item.restore_placeholders()
    assert item.translation_lines == ["你好" + "".join(segments)]


def test_standard_controls_do_not_split_long_custom_candidates() -> None:
    """标准控制符不能只吞掉疑似自定义控制符的短前缀。"""
    rules = get_default_text_rules()
    item = TranslationItem(
        location_path="Map001.json/1/0/1",
        item_type="long_text",
        original_lines=[r"\nn[Name]こんにちは", r"\fiこんにちは", r"\G1こんにちは"],
    )

    item.build_placeholders(rules)

    assert item.original_lines_with_placeholders == [
        r"\nn[Name]こんにちは",
        r"\fiこんにちは",
        r"\G1こんにちは",
    ]
    uncovered = [
        candidate.original
        for line in item.original_lines
        for candidate in rules.iter_unprotected_control_sequence_candidates(line)
    ]
    assert uncovered == [r"\nn[Name]", r"\fi", r"\G1"]


def test_literal_escape_followed_by_text_is_not_long_candidate() -> None:
    """字面量短转义后接普通英文正文时仍按标准转义保护。"""
    rules = get_default_text_rules()
    item = TranslationItem(
        location_path="Map001.json/1/0/2",
        item_type="short_text",
        original_lines=[r"line\nnext value\ttext page\fnext"],
    )

    item.build_placeholders(rules)

    assert item.original_lines_with_placeholders == [
        "line"
        + LITERAL_LINE_BREAK_PLACEHOLDER
        + "next value"
        + LITERAL_ESCAPE_PLACEHOLDERS["\\t"]
        + "text page"
        + LITERAL_ESCAPE_PLACEHOLDERS["\\f"]
        + "next"
    ]
    assert rules.iter_unprotected_control_sequence_candidates(item.original_lines[0]) == []


def test_custom_rule_can_fully_protect_long_candidate_prefix() -> None:
    """自定义规则完整覆盖长候选时优先于标准短转义。"""
    rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(
                r"\\nn\[[^\]\r\n]+\]",
                "[CUSTOM_PLUGIN_NAME_{index}]",
            ),
            CustomPlaceholderRule.create(
                r"\\fi",
                "[CUSTOM_PLUGIN_FACE_IN_{index}]",
            ),
        ),
    )
    item = TranslationItem(
        location_path="Map001.json/1/0/2",
        item_type="long_text",
        original_lines=[r"\nn[Name]こんにちは", r"\fiこんにちは"],
    )

    item.build_placeholders(rules)

    assert item.original_lines_with_placeholders == [
        "[CUSTOM_PLUGIN_NAME_1]こんにちは",
        "[CUSTOM_PLUGIN_FACE_IN_2]こんにちは",
    ]
    assert [
        candidate.original
        for line in item.original_lines
        for candidate in rules.iter_unprotected_control_sequence_candidates(line)
    ] == []


def test_custom_placeholder_rules_accept_current_pcre2_inline_option() -> None:
    """普通占位符规则按当前 PCRE2 内联选项校验。"""
    rule = CustomPlaceholderRule.create(
        r"(?a:@PLUGIN\[[^\]]+\])",
        "[CUSTOM_PLUGIN_MARKER_{index}]",
    )

    rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(rule,),
    )

    assert rules.custom_placeholder_rules == (rule,)


def test_custom_rule_covering_nested_candidate_counts_as_covered() -> None:
    """自定义规则覆盖嵌套参数整体时，半截扫描候选也算已保护。"""
    rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(
                r"\\nn\[\\v\[[0-9]+\]\]",
                "[CUSTOM_PLUGIN_VARIABLE_NAME_{index}]",
            ),
        ),
    )

    assert rules.iter_unprotected_control_sequence_candidates(r"\nn[\v[527]]こんにちは") == []


def test_structured_placeholder_rules_accept_current_pcre2_inline_option() -> None:
    """结构化占位符规则按当前 PCRE2 内联选项校验。"""
    rule = StructuredPlaceholderRule.create(
        rule_name="INLINE_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?a:(?<prefix><label>))(?<text>[^<]+)(?<suffix></label>)",
        translatable_group="text",
        protected_groups={
            "prefix": "[CUSTOM_INLINE_LABEL_PREFIX_{index}]",
            "suffix": "[CUSTOM_INLINE_LABEL_SUFFIX_{index}]",
        },
    )

    rules = TextRules.from_setting(
        TextRulesSetting(),
        structured_placeholder_rules=(rule,),
    )

    assert rules.structured_placeholder_rules == (rule,)


def test_text_rules_filter_resource_and_japanese_residual() -> None:
    """译文残留明显日文时应显式失败。"""
    rules = get_default_text_rules()

    with pytest.raises(ValueError, match="日文残留"):
        _check_source_residual_lines(rules, ["你好カ"])


def test_japanese_tail_allowlist_does_not_hide_untranslated_short_lines() -> None:
    """整行只剩日文尾音时仍按未翻译残留处理。"""
    rules = get_default_text_rules()

    with pytest.raises(ValueError, match="日文残留"):
        _check_source_residual_lines(rules, ["「なっ……」"])

    with pytest.raises(ValueError, match="日文残留"):
        _check_source_residual_lines(rules, ['"え？"'])

    _check_source_residual_lines(rules, ["已经好了よ"])


def test_text_rules_requires_configured_source_characters_for_translation() -> None:
    """原文必须包含平假名、片假名或汉字才进入正文翻译。"""
    rules = get_default_text_rules()

    assert is_source_text_required(rules, "こんにちは")
    assert is_source_text_required(rules, "テスト")
    assert is_source_text_required(rules, "勇者")
    assert not is_source_text_required(rules, "Untitled")
    assert not is_source_text_required(rules, "Back")
    assert not is_source_text_required(rules, "123")
    assert not is_source_text_required(rules, "img/pictures/Actor1.png")


def test_english_text_rules_extract_visible_text_and_skip_protocol_noise() -> None:
    """英文档案只提取玩家可见英文，跳过资源路径和脚本噪音。"""
    rules = TextRules.from_setting(
        TextRulesSetting(
            source_language="en",
            source_residual_label="英文",
            source_text_required_pattern=r"[A-Za-z][A-Za-z0-9'’_-]*",
            source_text_exclusion_profile="english_protocol_noise",
            source_residual_segment_pattern=r"[A-Za-z][A-Za-z0-9'’_-]*",
            source_residual_terms_ignore_case=True,
        )
    )

    assert is_source_text_required(rules, "Are you really going in there?")
    assert is_source_text_required(rules, "Open the old chest")
    assert is_source_text_required(rules, "Inventory")
    assert is_source_text_required(rules, "With this rope...")
    assert is_source_text_required(rules, "Command your nano-suit to inject this...")
    assert is_source_text_required(rules, "Although it looks strange, this weapon works.")
    assert is_source_text_required(rules, "Return to town")
    assert is_source_text_required(rules, "Let me handle this.")
    assert is_source_text_required(rules, "Pay $5 to enter.")
    assert is_source_text_required(rules, "Go east; then open the gate.")
    assert is_source_text_required(rules, "Use {item} to continue.")
    assert is_source_text_required(rules, "Look => move")
    assert is_source_text_required(rules, r"\c[14]The water level has dropped...")
    assert is_source_text_required(rules, "Auto")
    assert is_source_text_required(rules, "Default")
    assert is_source_text_required(rules, "GameOver")
    assert is_source_text_required(rules, "AutoSave")
    assert is_source_text_required(rules, "SkillTree")
    assert is_source_text_required(rules, "Route66")
    assert is_source_text_required(rules, "Save_File")
    assert not is_source_text_required(rules, r"\c[14]水池的水位已然降低...")
    assert not is_source_text_required(rules, "img/pictures/Actor1.png")
    assert not is_source_text_required(rules, "audio/se/Decision1.ogg")
    assert not is_source_text_required(rules, "damageFormula")
    assert not is_source_text_required(rules, "a.hpRate() >= 0.5")
    assert not is_source_text_required(rules, "this._window.visible = true")
    assert not is_source_text_required(rules, "return a.hpRate() >= 0.5;")
    assert not is_source_text_required(rules, "Math.max(a.atk, b.def)")
    assert not is_source_text_required(rules, "$gameVariables.value(1)")
    assert not is_source_text_required(rules, "const payload = {name: value};")
    assert not is_source_text_required(rules, "(value) => value + 1")
    assert not is_source_text_required(rules, "true")
    assert not is_source_text_required(rules, "123")


def test_english_source_residual_allows_default_ui_abbreviations() -> None:
    """英文档案不能依赖内置英文词表，应按源文复制片段判断残留。"""
    setting = build_text_rules_setting_for_language_profile("en")
    rules = TextRules.from_setting(setting)
    assert setting.allowed_source_residual_terms == []
    assert setting.source_residual_detection_profile == "english_source_copy"

    allowed_item = TranslationItem(
        location_path="Map001.json/1/0/0",
        item_type="short_text",
        original_lines=["Press the red switch before opening the old gate."],
        translation_lines=["按 A 键，CG 已解锁，Alice 加入队伍，Good Ending 开启。"],
    )
    check_source_residual_for_item(item=allowed_item, text_rules=rules, rule_set=None)

    leaked_item = allowed_item.model_copy(
        update={
            "translation_lines": ["不要 Press the red switch before opening 继续。"],
        }
    )
    with pytest.raises(ValueError, match="英文残留") as residual_error:
        check_source_residual_for_item(item=leaked_item, text_rules=rules, rule_set=None)
    residual_message = str(residual_error.value)
    assert "Press the red switch before opening" in residual_message
    assert "Alice" not in residual_message


def test_english_source_copy_thresholds_are_configurable() -> None:
    """英文源文复制残留阈值来自配置，不靠写死词表或特殊单词。"""
    default_rules = TextRules.from_setting(build_text_rules_setting_for_language_profile("en"))
    strict_rules = TextRules.from_setting(
        build_text_rules_setting_for_language_profile("en").model_copy(
            update={
                "english_source_copy_min_words": 2,
                "english_source_copy_min_letters": 6,
            }
        )
    )
    item = TranslationItem(
        location_path="Map001.json/1/0/1",
        item_type="short_text",
        original_lines=["Open the ancient gate."],
        translation_lines=["打开 Open the 门。"],
    )

    check_source_residual_for_item(item=item, text_rules=default_rules, rule_set=None)
    with pytest.raises(ValueError, match="英文残留"):
        check_source_residual_for_item(item=item, text_rules=strict_rules, rule_set=None)


def test_english_source_residual_without_original_checks_long_runs() -> None:
    """当前运行文件缺少原文上下文时，英文长句残留不能被静默放行。"""
    rules = TextRules.from_setting(build_text_rules_setting_for_language_profile("en"))

    _check_source_residual_lines(rules, ["按 A 键，CG 已解锁，Alice 加入队伍，Good Ending 开启。"])
    with pytest.raises(ValueError, match="Press the red switch before opening") as error_info:
        _check_source_residual_lines(rules, ["不要 Press the red switch before opening 继续。"])

    assert "Alice" not in str(error_info.value)


def test_structural_source_residual_rule_only_masks_protocol_terms() -> None:
    """结构性源文例外只放行协议词，显示文本仍会被残留检查拦截。"""
    rules = get_default_text_rules()
    rule_set = SourceResidualRuleSet.from_records(
        [
            SourceResidualRuleRecord(
                rule_id="structural:0",
                rule_type="structural",
                pattern_text=r"^(?P<protocol>なまえ):(?P<visible>.*)$",
                allowed_terms=["なまえ"],
                check_group="visible",
                reason="protocol_label",
            )
        ]
    )
    protocol_only_item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=["なまえ:こんにちは"],
        translation_lines=["なまえ:你好"],
    )
    leaked_visible_item = protocol_only_item.model_copy(
        update={"translation_lines": ["なまえ:こんにちは"]}
    )
    leaked_allowed_term_in_visible_item = protocol_only_item.model_copy(
        update={"translation_lines": ["なまえ:なまえ"]}
    )
    empty_visible_group_item = protocol_only_item.model_copy(
        update={"translation_lines": ["なまえ:"]}
    )

    check_source_residual_for_item(
        item=protocol_only_item,
        text_rules=rules,
        rule_set=rule_set,
    )
    with pytest.raises(ValueError, match="日文残留"):
        check_source_residual_for_item(
            item=leaked_visible_item,
            text_rules=rules,
            rule_set=rule_set,
        )
    with pytest.raises(ValueError, match="日文残留"):
        check_source_residual_for_item(
            item=leaked_allowed_term_in_visible_item,
            text_rules=rules,
            rule_set=rule_set,
        )
    with pytest.raises(ValueError, match="日文残留"):
        check_source_residual_for_item(
            item=empty_visible_group_item,
            text_rules=rules,
            rule_set=rule_set,
        )


def test_structural_source_residual_rule_respects_ignore_case() -> None:
    """英文结构性协议词例外遵守大小写忽略，但显示文本仍按源文复制检查。"""
    rules = TextRules.from_setting(
        build_text_rules_setting_for_language_profile("en").model_copy(
            update={
                "english_source_copy_min_words": 3,
                "english_source_copy_min_letters": 10,
            }
        )
    )
    rule_set = SourceResidualRuleSet.from_records(
        [
            SourceResidualRuleRecord(
                rule_id="structural:0",
                rule_type="structural",
                pattern_text=r"^(?P<protocol>label):(?P<visible>.*)$",
                allowed_terms=["LABEL"],
                check_group="visible",
                reason="protocol_label",
            )
        ]
    )
    protocol_only_item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=["LABEL:Open the ancient gate"],
        translation_lines=["label:你好"],
    )
    leaked_visible_item = protocol_only_item.model_copy(
        update={"translation_lines": ["label:Open the ancient gate"]}
    )

    check_source_residual_for_item(
        item=protocol_only_item,
        text_rules=rules,
        rule_set=rule_set,
    )
    with pytest.raises(ValueError, match="英文残留"):
        check_source_residual_for_item(
            item=leaked_visible_item,
            text_rules=rules,
            rule_set=rule_set,
        )


def test_structural_source_residual_rule_rejects_corrupt_records() -> None:
    """数据库里的损坏结构性例外规则在 native 执行前显式失败。"""
    rules = get_default_text_rules()
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=["こんにちは"],
        translation_lines=["こんにちは"],
    )
    corrupt_rule_set = SourceResidualRuleSet.from_records(
        [
            SourceResidualRuleRecord(
                rule_id="structural:broken",
                rule_type="structural",
                pattern_text="[",
                allowed_terms=["LABEL"],
                check_group="visible",
                reason="broken",
            )
        ]
    )
    missing_group_rule_set = SourceResidualRuleSet.from_records(
        [
            SourceResidualRuleRecord(
                rule_id="structural:missing_group",
                rule_type="structural",
                pattern_text=r"^(?<protocol>label):(?<visible>.*)$",
                allowed_terms=["LABEL"],
                check_group="missing",
                reason="broken",
            )
        ]
    )
    pcre2_rule_set = SourceResidualRuleSet.from_records(
        [
            SourceResidualRuleRecord(
                rule_id="structural:pcre2_lookbehind",
                rule_type="structural",
                pattern_text=r"(?<=<label>)(?<visible>[^<]+)(?=</label>)",
                allowed_terms=["label"],
                check_group="visible",
                reason="current_pcre2",
            )
        ]
    )

    with pytest.raises(ValueError, match="PCRE2 pattern 损坏"):
        check_source_residual_for_item(item=item, text_rules=rules, rule_set=corrupt_rule_set)
    with pytest.raises(ValueError, match="缺少命名分组"):
        check_source_residual_for_item(item=item, text_rules=rules, rule_set=missing_group_rule_set)
    with pytest.raises(ValueError, match="日文残留"):
        check_source_residual_for_item(item=item, text_rules=rules, rule_set=pcre2_rule_set)


def test_position_source_residual_rule_rejects_corrupt_records() -> None:
    """数据库里的损坏位置例外规则不能被静默忽略。"""
    with pytest.raises(ValueError, match="缺少内部位置"):
        _ = SourceResidualRuleSet.from_records(
            [
                SourceResidualRuleRecord(
                    rule_id="position:broken",
                    rule_type="position",
                    location_path="",
                    allowed_terms=["Alice"],
                    reason="broken",
                )
            ]
        )

    with pytest.raises(ValueError, match="缺少允许保留"):
        _ = SourceResidualRuleSet.from_records(
            [
                SourceResidualRuleRecord(
                    rule_id="position:broken",
                    rule_type="position",
                    location_path="Map001.json/1/0/0",
                    allowed_terms=[],
                    reason="broken",
                )
            ]
        )


def test_note_tag_file_pattern_uses_fnmatch_glob_not_regex() -> None:
    """Note 标签文件键是 fnmatch 风格通配模式，不是正则表达式。"""
    assert note_file_pattern_matches(file_name="Map001.json", file_pattern="Map*.json")
    assert not note_file_pattern_matches(file_name="Map001.json", file_pattern=r"Map\d+\.json")


def test_text_rules_keep_book_title_quote_during_extraction() -> None:
    """提取阶段不剥离外层日文书名号，避免写回时丢失玩家可见符号。"""
    rules = get_default_text_rules()

    assert rules.normalize_extraction_text("『リコの銀行』") == "『リコの銀行』"
    assert is_source_text_required(rules, "『リコの銀行』")


def test_text_rules_normalize_translation_lines_strips_outer_whitespace() -> None:
    """译文保存前清理每行首尾空白，保留行内空白。"""
    rules = get_default_text_rules()

    assert rules.normalize_translation_lines(["　你好　", "甲　乙", "\t再见 "]) == [
        "你好",
        "甲　乙",
        "再见",
    ]


def test_text_rules_can_apply_custom_placeholder_json_rules() -> None:
    """自定义正则规则会在标准 RMMZ 控制符之外保护特殊片段。"""
    rules = TextRules.from_setting(
        TextRulesSetting(line_width_count_pattern="@"),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(r"@V\[\d+\]", "[CUSTOM_AT_VARIABLE_{index}]"),
            CustomPlaceholderRule.create(r"<tag:[^>]+>", "[CUSTOM_INLINE_TAG_{index}]"),
        ),
    )
    item = TranslationItem(
        location_path="Map001.json/1/0/0",
        item_type="long_text",
        original_lines=["こんにちは@V[1]<tag:abc>\\V[2]"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == [
        "こんにちは[CUSTOM_AT_VARIABLE_1][CUSTOM_INLINE_TAG_2][RMMZ_VARIABLE_2]"
    ]

    item.translation_lines_with_placeholders = [
        "你好[CUSTOM_AT_VARIABLE_1][CUSTOM_INLINE_TAG_2][RMMZ_VARIABLE_2]"
    ]
    item.verify_placeholders(rules)
    item.restore_placeholders()
    assert item.translation_lines == ["你好@V[1]<tag:abc>\\V[2]"]
    assert count_line_width_chars("@@中文", rules) == 2
    assert count_line_width_chars("@", rules) == 1


def test_custom_prefix_control_keeps_adjacent_dialogue_translatable() -> None:
    """无参数插件控制符可以只保护前缀，后面紧贴的正文继续交给模型。"""
    rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(r"\\Shake", "[CUSTOM_PLUGIN_SHAKE_MARKER_{index}]"),
        ),
    )
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=[r"\ShakeStop this!!!"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == ["[CUSTOM_PLUGIN_SHAKE_MARKER_1]Stop this!!!"]

    item.translation_lines_with_placeholders = ["[CUSTOM_PLUGIN_SHAKE_MARKER_1]住手！！！"]
    item.verify_placeholders(rules)
    item.restore_placeholders()
    assert item.translation_lines == [r"\Shake住手！！！"]


def test_structured_placeholder_rule_keeps_shell_and_translates_inner_text() -> None:
    """结构化规则只保护协议外壳，中间显示文本继续交给模型翻译。"""
    structured_rule = StructuredPlaceholderRule.create(
        rule_name="MINI_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
        translatable_group="text",
        protected_groups={
            "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
            "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
        },
    )
    rules = TextRules.from_setting(
        TextRulesSetting(),
        structured_placeholder_rules=(structured_rule,),
    )
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=["<Mini Label: Alraune>"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == [
        "[CUSTOM_MINI_LABEL_OPEN_1]Alraune[CUSTOM_MINI_LABEL_CLOSE_1]"
    ]

    item.translation_lines_with_placeholders = [
        "[CUSTOM_MINI_LABEL_OPEN_1]阿尔劳娜[CUSTOM_MINI_LABEL_CLOSE_1]"
    ]
    item.verify_placeholders(rules)
    item.restore_placeholders()
    assert item.translation_lines == ["<Mini Label: 阿尔劳娜>"]


def test_structured_placeholder_rule_uses_distinct_indices_for_same_offsets() -> None:
    """多行同位置命中不同协议外壳时，结构化占位符编号不能跨行撞号。"""
    structured_rule = StructuredPlaceholderRule.create(
        rule_name="TAGGED_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?P<open><Label\s+id=\d+:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
        translatable_group="text",
        protected_groups={
            "open": "[CUSTOM_TAGGED_LABEL_OPEN_{index}]",
            "close": "[CUSTOM_TAGGED_LABEL_CLOSE_{index}]",
        },
    )
    rules = TextRules.from_setting(
        TextRulesSetting(),
        structured_placeholder_rules=(structured_rule,),
    )
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="long_text",
        original_lines=["<Label id=1: Alice>", "<Label id=2: Carol>"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == [
        "[CUSTOM_TAGGED_LABEL_OPEN_1]Alice[CUSTOM_TAGGED_LABEL_CLOSE_1]",
        "[CUSTOM_TAGGED_LABEL_OPEN_2]Carol[CUSTOM_TAGGED_LABEL_CLOSE_2]",
    ]

    item.translation_lines_with_placeholders = [
        "[CUSTOM_TAGGED_LABEL_OPEN_1]爱丽丝[CUSTOM_TAGGED_LABEL_CLOSE_1]",
        "[CUSTOM_TAGGED_LABEL_OPEN_2]卡萝尔[CUSTOM_TAGGED_LABEL_CLOSE_2]",
    ]
    item.verify_placeholders(rules)
    item.restore_placeholders()
    assert item.translation_lines == ["<Label id=1: 爱丽丝>", "<Label id=2: 卡萝尔>"]


def test_structured_placeholder_rule_rejects_missing_shell_marker() -> None:
    """模型漏掉结构化协议外壳任意一侧时必须保存失败。"""
    structured_rule = StructuredPlaceholderRule.create(
        rule_name="MINI_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
        translatable_group="text",
        protected_groups={
            "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
            "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
        },
    )
    rules = TextRules.from_setting(
        TextRulesSetting(),
        structured_placeholder_rules=(structured_rule,),
    )
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=["<Mini Label: Alraune>"],
    )

    item.build_placeholders(rules)
    item.translation_lines_with_placeholders = ["[CUSTOM_MINI_LABEL_OPEN_1]阿尔劳娜"]

    with pytest.raises(ValueError, match="CUSTOM_MINI_LABEL_CLOSE_1"):
        item.verify_placeholders(rules)


def test_structured_placeholder_rule_rejects_normal_rule_overlap() -> None:
    """普通正则规则不能抢结构化规则的外壳保护范围。"""
    structured_rule = StructuredPlaceholderRule.create(
        rule_name="MINI_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
        translatable_group="text",
        protected_groups={
            "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
            "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
        },
    )
    rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(r">", "[CUSTOM_RAW_CLOSE_{index}]"),
        ),
        structured_placeholder_rules=(structured_rule,),
    )
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=["<Mini Label: Alraune>"],
    )

    with pytest.raises(ValueError, match="重叠"):
        item.build_placeholders(rules)


def test_structured_placeholder_rule_rejects_translatable_group_overlap() -> None:
    """可翻译分组不能再被普通正则规则保护，否则模型看不到显示文本。"""
    structured_rule = StructuredPlaceholderRule.create(
        rule_name="MINI_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
        translatable_group="text",
        protected_groups={
            "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
            "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
        },
    )
    rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(r"Alraune", "[CUSTOM_NAME_{index}]"),
        ),
        structured_placeholder_rules=(structured_rule,),
    )
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=["<Mini Label: Alraune>"],
    )

    with pytest.raises(ValueError, match="可翻译文本分组"):
        item.build_placeholders(rules)


def test_structured_placeholder_rule_allows_standard_control_in_translatable_group() -> None:
    """结构化规则的可翻译正文里可以包含内置 RPG Maker 控制符。"""
    structured_rule = StructuredPlaceholderRule.create(
        rule_name="D_TEXT_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?P<open>^D_TEXT\s+)(?P<text>.*?)(?P<close>\s+48$)",
        translatable_group="text",
        protected_groups={
            "open": "[CUSTOM_D_TEXT_OPEN_{index}]",
            "close": "[CUSTOM_D_TEXT_CLOSE_{index}]",
        },
    )
    rules = TextRules.from_setting(
        TextRulesSetting(),
        structured_placeholder_rules=(structured_rule,),
    )
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="short_text",
        original_lines=[r"D_TEXT \c[17]決定ボタンを連打しろ！ 48"],
    )

    item.build_placeholders(rules)

    assert item.original_lines_with_placeholders == [
        "[CUSTOM_D_TEXT_OPEN_1][RMMZ_TEXT_COLOR_17]決定ボタンを連打しろ！[CUSTOM_D_TEXT_CLOSE_1]"
    ]
    item.translation_lines_with_placeholders = [
        "[CUSTOM_D_TEXT_OPEN_1][RMMZ_TEXT_COLOR_17]狂按决定键！[CUSTOM_D_TEXT_CLOSE_1]"
    ]
    item.verify_placeholders(rules)
    item.restore_placeholders()
    assert item.translation_lines == [r"D_TEXT \c[17]狂按决定键！ 48"]


def test_unprotected_control_sequences_must_stay_exact() -> None:
    """未被规则覆盖的畸形控制符也必须在译文中原样保留。"""
    rules = get_default_text_rules()
    item = TranslationItem(
        location_path="CommonEvents.json/99/293",
        item_type="long_text",
        original_lines=[r"\F3[66」「ふーん……？」"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == [r"\F3[66」「ふーん……？」"]

    item.translation_lines_with_placeholders = [r"\F3[66」「唔——嗯……？」"]
    item.verify_placeholders(rules)

    item.translation_lines_with_placeholders = [r"\F3[60」「唔——嗯……？」"]
    with pytest.raises(ValueError, match="疑似控制符不一致"):
        item.verify_placeholders(rules)

    item.translation_lines_with_placeholders = [r"\F3[66]「唔——嗯……？」"]
    with pytest.raises(ValueError, match="疑似控制符不一致"):
        item.verify_placeholders(rules)


def test_unprotected_control_sequences_report_added_unknown_escape() -> None:
    """译文新增未覆盖反斜杠片段时必须显式失败。"""
    rules = get_default_text_rules()
    item = TranslationItem(
        location_path="CommonEvents.json/1/0",
        item_type="long_text",
        original_lines=["こんにちは"],
    )

    item.build_placeholders(rules)
    item.translation_lines_with_placeholders = [r"你好\X下一行"]

    with pytest.raises(ValueError, match=r"\\X"):
        item.verify_placeholders(rules)


def test_literal_line_break_placeholder_structure_rejects_additions() -> None:
    """字面量反斜杠 n 是单字段结构，不能被译文额外新增。"""
    rules = get_default_text_rules()
    item = TranslationItem(
        location_path="plugins.js/1/message",
        item_type="short_text",
        original_lines=["説明\\n本文"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == [f"説明{LITERAL_LINE_BREAK_PLACEHOLDER}本文"]

    item.translation_lines_with_placeholders = [
        f"说明{LITERAL_LINE_BREAK_PLACEHOLDER}正文{LITERAL_LINE_BREAK_PLACEHOLDER}补充"
    ]
    with pytest.raises(ValueError, match="字面量换行标记数量不一致"):
        validate_translation_text_structure(
            item=item,
            translation_lines=["说明\\n正文\\n补充"],
            text_rules=rules,
            translation_lines_with_placeholders=item.translation_lines_with_placeholders,
        )


def test_real_line_break_placeholder_roundtrips_short_text() -> None:
    """字段内部真实换行会先占位，译文通过后再恢复。"""
    rules = get_default_text_rules()
    item = TranslationItem(
        location_path="Items.json/1/description",
        item_type="short_text",
        original_lines=["説明\n本文"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == [
        f"説明{REAL_LINE_BREAK_PLACEHOLDER}本文"
    ]

    item.translation_lines_with_placeholders = [
        f"说明{REAL_LINE_BREAK_PLACEHOLDER}正文"
    ]
    item.verify_placeholders(rules)
    item.restore_placeholders()
    assert item.translation_lines == ["说明\n正文"]


def test_real_line_break_placeholder_rejects_missing_marker() -> None:
    """模型把真实换行标记改回视觉换行时会被控制符校验拒绝。"""
    rules = get_default_text_rules()
    item = TranslationItem(
        location_path="Items.json/1/description",
        item_type="short_text",
        original_lines=["説明\n本文"],
    )

    item.build_placeholders(rules)
    item.translation_lines_with_placeholders = ["说明\n正文"]

    with pytest.raises(ValueError, match=REAL_LINE_BREAK_PLACEHOLDER):
        item.verify_placeholders(rules)


def test_custom_placeholder_rules_load_from_explicit_json_file(tmp_path: Path) -> None:
    """显式自定义占位符规则 JSON 使用正则字符串作为键、占位符模板作为值。"""
    rules_path = tmp_path / "custom_placeholder_rules.json"
    _ = rules_path.write_text(
        json.dumps({r"@name\[[^\]]+\]": "[CUSTOM_NAME_{index}]"}),
        encoding="utf-8",
    )

    custom_rules = load_custom_placeholder_rules_file(rules_path=rules_path)
    rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=custom_rules,
    )
    item = TranslationItem(
        location_path="Map001.json/1/0/0",
        item_type="short_text",
        original_lines=["@name[アリス]"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == ["[CUSTOM_NAME_1]"]


def test_custom_placeholder_rules_do_not_expose_app_home_loader() -> None:
    """配置公共门面不暴露应用运行目录隐式规则入口。"""
    assert not hasattr(config, "load_custom_placeholder_rules")
    assert not hasattr(config, "resolve_custom_placeholder_rules_path")


def test_custom_placeholder_rules_load_from_cli_json_string() -> None:
    """CLI JSON 字符串会作为本次运行的规则来源。"""
    custom_rules = load_custom_placeholder_rules_text(
        json.dumps({r"\\F\[[^\]]+\]": "[CUSTOM_FACE_PORTRAIT_{index}]"})
    )
    rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=custom_rules,
    )
    item = TranslationItem(
        location_path="Map001.json/1/0/0",
        item_type="short_text",
        original_lines=[r"\F[FinF]こんにちは"],
    )

    item.build_placeholders(rules)
    assert item.original_lines_with_placeholders == ["[CUSTOM_FACE_PORTRAIT_1]こんにちは"]


def test_custom_placeholder_rules_explicit_missing_file_fails(tmp_path: Path) -> None:
    """显式读取的规则文件不存在时应直接失败。"""
    with pytest.raises(FileNotFoundError):
        _ = load_custom_placeholder_rules_file(rules_path=tmp_path / "missing.json")


def test_custom_placeholder_rules_empty_cli_json_string_fails() -> None:
    """CLI 规则字符串为空时应直接失败。"""
    with pytest.raises(ValueError):
        _ = load_custom_placeholder_rules_text("")


def test_custom_placeholder_rules_cli_keeps_string_values_strict() -> None:
    """CLI 自定义占位符规则值仍必须是真实字符串。"""
    with pytest.raises(TypeError, match="必须是字符串"):
        _ = load_custom_placeholder_rules_text(json.dumps({r"\\Face\[[^\]]+\]": 123}, ensure_ascii=False))


def test_custom_placeholder_rules_import_normalizes_integer_template() -> None:
    """Agent 导入自定义占位符规则时，整数模板先按文本字段规范化。"""
    with pytest.raises(ValueError, match="必须生成形如"):
        _ = load_custom_placeholder_rules_import_text(
            json.dumps({r"\\Face\[[^\]]+\]": 123}, ensure_ascii=False)
        )


def test_custom_placeholder_rules_import_rejects_boolean_template() -> None:
    """Agent 导入自定义占位符规则时，布尔模板无效。"""
    with pytest.raises(TypeError, match="bool"):
        _ = load_custom_placeholder_rules_import_text(
            json.dumps({r"\\Face\[[^\]]+\]": True}, ensure_ascii=False)
        )


def test_structured_placeholder_rules_cli_keeps_string_values_strict() -> None:
    """CLI 结构化占位符规则值仍必须是真实字符串。"""
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": 123,
                    "pattern": r"(?P<open><tag>)(?P<text>[^<]+)(?P<close></tag>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_TAG_OPEN_{index}]",
                        "close": "[CUSTOM_TAG_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    with pytest.raises(TypeError, match="必须是字符串"):
        _ = load_structured_placeholder_rules_text(rules_text)


def test_structured_placeholder_rules_import_normalizes_integer_name() -> None:
    """Agent 导入结构化占位符规则时，整数 name 先按文本字段规范化。"""
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": 123,
                    "pattern": r"(?P<open><tag>)(?P<text>[^<]+)(?P<close></tag>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_TAG_OPEN_{index}]",
                        "close": "[CUSTOM_TAG_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    with pytest.raises(ValueError, match="大写标识"):
        _ = load_structured_placeholder_rules_import_text(rules_text)


def test_structured_placeholder_rules_import_rejects_boolean_template() -> None:
    """Agent 导入结构化占位符规则时，布尔模板无效。"""
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "TAG",
                    "pattern": r"(?P<open><tag>)(?P<text>[^<]+)(?P<close></tag>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": True,
                        "close": "[CUSTOM_TAG_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    with pytest.raises(TypeError, match="bool"):
        _ = load_structured_placeholder_rules_import_text(rules_text)
