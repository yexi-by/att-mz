"""应用层可预期业务失败类型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StableErrorIssue:
    """稳定错误码和面向用户的中文说明。"""

    code: str
    message: str


class ApplicationBusinessError(RuntimeError):
    """表示应用层已经识别且应直接展示给用户的业务失败。"""


class WorkflowGateError(ApplicationBusinessError):
    """表示翻译或写文件前置流程检查未通过。"""


class WriteBackGateError(ApplicationBusinessError):
    """表示写入游戏文件前质量或写入条件检查未通过。"""


_NATIVE_ERROR_MESSAGES: dict[str, str] = {
    "text_index_contract_changed": (
        "当前文本范围索引的契约版本不符合当前程序要求，翻译、质量报告和写进游戏文件不能继续。"
        "下一步：请重新生成当前文本范围索引；如果仍失败，请重新构建 Rust 原生扩展或更新发行包。"
    ),
    "plugin_source_selector_filtered": (
        "插件源码规则引用的 selector 已被当前规则过滤，相关插件源码文本不会进入可写范围。"
        "下一步：请重新导出插件源码候选，修正规则后重新导入，并重新生成当前文本范围索引。"
    ),
    "plugin_source_ast_missing": (
        "插件源码规则引用的 AST selector 不在当前插件源码 AST 地图中，相关插件源码文本不能安全写回。"
        "下一步：请重新导出插件源码 AST 地图，按当前 selector 修正规则后重新生成当前文本范围索引。"
    ),
    "nonstandard_data_rule_unmatched": (
        "非标准 data 规则没有命中当前游戏数据，相关 data 文本不会进入可写范围。"
        "下一步：请重新导出非标准 data 候选，修正规则后重新导入，并重新生成当前文本范围索引。"
    ),
    "note_tag_rule_unmatched": (
        "Note 标签规则没有命中当前游戏数据，相关 Note 文本不会进入可写范围。"
        "下一步：请重新导出 Note 标签候选，修正规则后重新导入，并重新生成当前文本范围索引。"
    ),
    "path_template_invalid": (
        "规则里的路径模板不是当前支持的 JSONPath 形态，相关规则不能参与文本提取。"
        "下一步：请修正规则中的路径模板后重新导入，并重新生成当前文本范围索引。"
    ),
    "stale_plugin_source_rules": (
        "插件源码规则与当前插件源码不一致，相关插件源码文本不能安全写回。"
        "下一步：请重新导出插件源码候选，修正规则后重新导入，并重新生成当前文本范围索引。"
    ),
    "plugin_source_review_incomplete": (
        "插件源码支线还有候选没有归入翻译或排除，插件源码文本不能继续进入后续流程。"
        "下一步：请补全插件源码规则后重新生成当前文本范围索引。"
    ),
    "plugin_source_candidate_contract_invalid": (
        "插件源码候选事实不符合当前契约，插件源码文本不能安全写回。"
        "下一步：请重新生成当前文本范围索引；如果仍失败，请重新构建 Rust 原生扩展或更新发行包。"
    ),
    "stale_nonstandard_data_rules": (
        "非标准 data 规则与当前游戏数据不一致，相关 data 文本不能安全写回。"
        "下一步：请重新导出非标准 data 候选，修正规则后重新导入，并重新生成当前文本范围索引。"
    ),
    "nonstandard_data_review_incomplete": (
        "非标准 data 支线还有候选没有归入翻译或排除，相关 data 文本不能继续进入后续流程。"
        "下一步：请补全非标准 data 规则后重新生成当前文本范围索引。"
    ),
}


def normalize_native_error_issue(code: str, message: str) -> StableErrorIssue:
    """把 Rust/native 错误码映射成稳定、可行动的中文说明。"""
    public_message = _NATIVE_ERROR_MESSAGES.get(code)
    if public_message is None:
        return StableErrorIssue(code=code, message=message)
    public_message = _with_detail_before_next_action(public_message, message)
    return StableErrorIssue(code=code, message=public_message)


def normalize_text_index_gate_error_issue(message: str) -> StableErrorIssue:
    """把读取 Rust gate facts 的失败映射成稳定 workflow gate code。"""
    if "契约版本不匹配" in message or "workflow_gate_prechecked" in message:
        return normalize_native_error_issue("text_index_contract_changed", message)
    if "缺少" in message or "不可读取" in message:
        return StableErrorIssue(
            code="text_index_gate_facts_missing",
            message=(
                "当前文本范围索引缺少 Rust gate facts，翻译、质量报告和写进游戏文件不能继续。"
                f"{_detail_sentence(message)}"
                "下一步：请重新生成当前文本范围索引。"
            ),
        )
    return StableErrorIssue(
            code="text_index_gate_facts_invalid",
            message=(
                "当前文本范围索引里的 Rust gate facts 不符合当前契约，翻译、质量报告和写进游戏文件不能继续。"
                f"{_detail_sentence(message)}"
                "下一步：请重新生成当前文本范围索引。"
            ),
        )


def _detail_sentence(message: str) -> str:
    detail = message.strip()
    if not detail:
        return ""
    return f"原因：{detail.rstrip('。')}。"


def _with_detail_before_next_action(public_message: str, detail_message: str) -> str:
    detail = _detail_sentence(detail_message)
    if not detail:
        return public_message
    next_action_marker = "下一步："
    if next_action_marker not in public_message:
        return f"{public_message}{detail}"
    before_next_action, next_action = public_message.split(next_action_marker, 1)
    return f"{before_next_action}{detail}{next_action_marker}{next_action}"


__all__ = [
    "ApplicationBusinessError",
    "StableErrorIssue",
    "WorkflowGateError",
    "WriteBackGateError",
    "normalize_native_error_issue",
    "normalize_text_index_gate_error_issue",
]
