"""外部文本规则审查领域定义。"""

from typing import Literal

type RuleRuntimeDomain = Literal[
    "plugin_config",
    "event_commands",
    "note_tags",
    "placeholders",
    "structured_placeholders",
    "mv_virtual_namebox",
]

type RuleReviewDomain = Literal[
    "plugin_text",
    "event_command_text",
    "note_tag_text",
    "placeholder_rules",
    "structured_placeholder_rules",
    "mv_virtual_namebox",
]

PLUGIN_TEXT_RULE_DOMAIN: RuleReviewDomain = "plugin_text"
EVENT_COMMAND_TEXT_RULE_DOMAIN: RuleReviewDomain = "event_command_text"
NOTE_TAG_TEXT_RULE_DOMAIN: RuleReviewDomain = "note_tag_text"
PLACEHOLDER_RULE_DOMAIN: RuleReviewDomain = "placeholder_rules"
STRUCTURED_PLACEHOLDER_RULE_DOMAIN: RuleReviewDomain = "structured_placeholder_rules"
MV_VIRTUAL_NAMEBOX_RULE_DOMAIN: RuleReviewDomain = "mv_virtual_namebox"


def parse_rule_review_domain(value: str) -> RuleReviewDomain:
    """校验并收窄数据库中的外部规则审查领域。"""
    if value == PLUGIN_TEXT_RULE_DOMAIN:
        return PLUGIN_TEXT_RULE_DOMAIN
    if value == EVENT_COMMAND_TEXT_RULE_DOMAIN:
        return EVENT_COMMAND_TEXT_RULE_DOMAIN
    if value == NOTE_TAG_TEXT_RULE_DOMAIN:
        return NOTE_TAG_TEXT_RULE_DOMAIN
    if value == PLACEHOLDER_RULE_DOMAIN:
        return PLACEHOLDER_RULE_DOMAIN
    if value == STRUCTURED_PLACEHOLDER_RULE_DOMAIN:
        return STRUCTURED_PLACEHOLDER_RULE_DOMAIN
    if value == MV_VIRTUAL_NAMEBOX_RULE_DOMAIN:
        return MV_VIRTUAL_NAMEBOX_RULE_DOMAIN
    raise ValueError(f"未知外部规则审查领域: {value}")


def rule_runtime_domain_for_review_domain(value: RuleReviewDomain) -> RuleRuntimeDomain:
    """把旧审查域名映射到当前统一 rule_runtime domain。"""
    if value == PLUGIN_TEXT_RULE_DOMAIN:
        return "plugin_config"
    if value == EVENT_COMMAND_TEXT_RULE_DOMAIN:
        return "event_commands"
    if value == NOTE_TAG_TEXT_RULE_DOMAIN:
        return "note_tags"
    if value == PLACEHOLDER_RULE_DOMAIN:
        return "placeholders"
    if value == STRUCTURED_PLACEHOLDER_RULE_DOMAIN:
        return "structured_placeholders"
    if value == MV_VIRTUAL_NAMEBOX_RULE_DOMAIN:
        return "mv_virtual_namebox"
    raise ValueError(f"未知外部规则审查领域: {value}")


def rule_review_domain_for_runtime_domain(value: str) -> RuleReviewDomain:
    """把统一 rule_runtime domain 映射回当前 Python 审查域名。"""
    if value == "plugin_config":
        return PLUGIN_TEXT_RULE_DOMAIN
    if value == "event_commands":
        return EVENT_COMMAND_TEXT_RULE_DOMAIN
    if value == "note_tags":
        return NOTE_TAG_TEXT_RULE_DOMAIN
    if value == "placeholders":
        return PLACEHOLDER_RULE_DOMAIN
    if value == "structured_placeholders":
        return STRUCTURED_PLACEHOLDER_RULE_DOMAIN
    if value == "mv_virtual_namebox":
        return MV_VIRTUAL_NAMEBOX_RULE_DOMAIN
    raise ValueError(f"未知 rule_runtime domain: {value}")


__all__: list[str] = [
    "EVENT_COMMAND_TEXT_RULE_DOMAIN",
    "NOTE_TAG_TEXT_RULE_DOMAIN",
    "PLACEHOLDER_RULE_DOMAIN",
    "PLUGIN_TEXT_RULE_DOMAIN",
    "MV_VIRTUAL_NAMEBOX_RULE_DOMAIN",
    "RuleReviewDomain",
    "RuleRuntimeDomain",
    "STRUCTURED_PLACEHOLDER_RULE_DOMAIN",
    "parse_rule_review_domain",
    "rule_review_domain_for_runtime_domain",
    "rule_runtime_domain_for_review_domain",
]
