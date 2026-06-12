"""Workflow Gate 用户可见错误映射测试。"""

from __future__ import annotations

import pytest

from app.application.errors import normalize_native_error_issue


@pytest.mark.parametrize(
    "code",
    [
        "text_index_contract_changed",
        "plugin_source_selector_filtered",
        "plugin_source_ast_missing",
        "nonstandard_data_rule_unmatched",
        "note_tag_rule_unmatched",
        "path_template_invalid",
    ],
)
def test_native_error_mapping_explains_stable_user_action(code: str) -> None:
    """Rust 事实相关错误码必须映射为可行动的中文错误。"""
    mapped = normalize_native_error_issue(code, "native detail")

    assert mapped.code == code
    assert "下一步" in mapped.message
    assert "native detail" in mapped.message
