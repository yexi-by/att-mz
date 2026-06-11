"""外部文本规则审查领域定义。"""

from typing import Literal

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


__all__: list[str] = [
    "EVENT_COMMAND_TEXT_RULE_DOMAIN",
    "NOTE_TAG_TEXT_RULE_DOMAIN",
    "PLACEHOLDER_RULE_DOMAIN",
    "PLUGIN_TEXT_RULE_DOMAIN",
    "MV_VIRTUAL_NAMEBOX_RULE_DOMAIN",
    "RuleReviewDomain",
    "STRUCTURED_PLACEHOLDER_RULE_DOMAIN",
    "parse_rule_review_domain",
]
