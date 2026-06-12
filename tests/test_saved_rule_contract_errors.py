"""已保存规则运行时错误的 Agent 契约测试。"""

from app.agent_toolkit.services.common import saved_rule_contract_issues_to_agent_issues
from app.agent_toolkit.reports import issue


def test_saved_rule_runtime_errors_are_reported_by_rule_domain() -> None:
    """已保存规则损坏时，公开错误码应指向规则域而不是底层正则引擎。"""
    issues = saved_rule_contract_issues_to_agent_issues(
        [
            issue(
                code="pcre2_compile_error",
                message="pattern 不是有效的 PCRE2 正则",
            )
        ],
        invalid_code="placeholder_rules_invalid",
    )

    assert len(issues) == 1
    assert issues[0].code == "placeholder_rules_invalid"
    assert issues[0].message == "pattern 不是有效的 PCRE2 正则"
