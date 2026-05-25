"""应用层可预期业务失败类型。"""

from __future__ import annotations


class ApplicationBusinessError(RuntimeError):
    """表示应用层已经识别且应直接展示给用户的业务失败。"""


class WorkflowGateError(ApplicationBusinessError):
    """表示翻译或写文件前置流程检查未通过。"""


class WriteBackGateError(ApplicationBusinessError):
    """表示写入游戏文件前质量或写入条件检查未通过。"""


__all__ = [
    "ApplicationBusinessError",
    "WorkflowGateError",
    "WriteBackGateError",
]
