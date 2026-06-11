"""源语言档案。"""

from dataclasses import dataclass, field
from typing import cast

from app.config.schemas import TextRulesSetting
from app.language import SourceLanguage, SourceResidualDetectionProfile, SourceTextExclusionProfile


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    """描述某种源语言进入简体中文本地化流程时使用的规则。"""

    source_language: SourceLanguage
    residual_label: str
    source_text_required_pattern: str
    source_text_exclusion_profile: SourceTextExclusionProfile
    source_residual_segment_pattern: str
    source_residual_detection_profile: SourceResidualDetectionProfile
    english_source_copy_min_words: int = 4
    english_source_copy_min_letters: int = 12
    source_residual_allowed_chars: tuple[str, ...] = field(default_factory=tuple)
    source_residual_allowed_tail_chars: tuple[str, ...] = field(default_factory=tuple)
    allowed_source_residual_terms: tuple[str, ...] = field(default_factory=tuple)
    source_residual_terms_ignore_case: bool = False


JAPANESE_PROFILE = LanguageProfile(
    source_language="ja",
    residual_label="日文",
    source_text_required_pattern=r"[ぁ-んァ-ヶ一-龯ー]+",
    source_text_exclusion_profile="none",
    source_residual_segment_pattern=r"[ぁ-んァ-ヶー]+",
    source_residual_detection_profile="japanese_strict",
    source_residual_allowed_chars=("っ", "ッ", "ー", "・", "。", "～", "…"),
    source_residual_allowed_tail_chars=(
        "あ",
        "い",
        "う",
        "え",
        "お",
        "っ",
        "ッ",
        "ん",
        "ー",
        "よ",
        "ね",
        "な",
        "か",
    ),
)

ENGLISH_PROFILE = LanguageProfile(
    source_language="en",
    residual_label="英文",
    source_text_required_pattern=r"[A-Za-z][A-Za-z0-9'’_-]*",
    source_text_exclusion_profile="english_protocol_noise",
    source_residual_segment_pattern=r"[A-Za-z][A-Za-z0-9'’_-]*",
    source_residual_detection_profile="english_source_copy",
    source_residual_terms_ignore_case=True,
)

LANGUAGE_PROFILES: dict[SourceLanguage, LanguageProfile] = {
    "ja": JAPANESE_PROFILE,
    "en": ENGLISH_PROFILE,
}


def language_profile(source_language: SourceLanguage) -> LanguageProfile:
    """读取指定源语言的语言档案。"""
    return LANGUAGE_PROFILES[source_language]


def build_text_rules_setting_for_language_profile(source_language: SourceLanguage) -> TextRulesSetting:
    """构造不依赖配置文件的源语言文本规则。"""
    profile = language_profile(source_language)
    return TextRulesSetting(
        source_language=profile.source_language,
        source_residual_label=profile.residual_label,
        source_text_required_pattern=profile.source_text_required_pattern,
        source_text_exclusion_profile=profile.source_text_exclusion_profile,
        source_residual_segment_pattern=profile.source_residual_segment_pattern,
        source_residual_detection_profile=profile.source_residual_detection_profile,
        english_source_copy_min_words=profile.english_source_copy_min_words,
        english_source_copy_min_letters=profile.english_source_copy_min_letters,
        source_residual_allowed_chars=list(profile.source_residual_allowed_chars),
        source_residual_allowed_tail_chars=list(profile.source_residual_allowed_tail_chars),
        allowed_source_residual_terms=list(profile.allowed_source_residual_terms),
        source_residual_terms_ignore_case=profile.source_residual_terms_ignore_case,
    )


def apply_language_profile_to_raw_config(
    *,
    raw_config: dict[str, object],
    source_language: SourceLanguage,
) -> None:
    """把语言档案的文本规则写入原始配置字典，后续 CLI 覆盖仍可继续覆盖这些值。"""
    profile = language_profile(source_language)
    text_rules = _read_or_create_section(raw_config, "text_rules")
    text_rules["source_language"] = profile.source_language
    text_rules["source_residual_label"] = profile.residual_label
    text_rules["source_text_required_pattern"] = profile.source_text_required_pattern
    text_rules["source_text_exclusion_profile"] = profile.source_text_exclusion_profile
    text_rules["source_residual_segment_pattern"] = profile.source_residual_segment_pattern
    text_rules["source_residual_detection_profile"] = profile.source_residual_detection_profile
    text_rules["english_source_copy_min_words"] = profile.english_source_copy_min_words
    text_rules["english_source_copy_min_letters"] = profile.english_source_copy_min_letters
    text_rules["source_residual_allowed_chars"] = list(profile.source_residual_allowed_chars)
    text_rules["source_residual_allowed_tail_chars"] = list(profile.source_residual_allowed_tail_chars)
    text_rules["allowed_source_residual_terms"] = list(profile.allowed_source_residual_terms)
    text_rules["source_residual_terms_ignore_case"] = profile.source_residual_terms_ignore_case


def _read_or_create_section(raw_config: dict[str, object], section_name: str) -> dict[str, object]:
    """读取配置段；缺失时创建空配置段。"""
    section = raw_config.get(section_name)
    if section is None:
        new_section: dict[str, object] = {}
        raw_config[section_name] = new_section
        return new_section
    if not isinstance(section, dict):
        raise ValueError(f"配置文件中 {section_name} 必须是表")
    return cast(dict[str, object], section)


__all__: list[str] = [
    "LanguageProfile",
    "apply_language_profile_to_raw_config",
    "build_text_rules_setting_for_language_profile",
    "language_profile",
]
